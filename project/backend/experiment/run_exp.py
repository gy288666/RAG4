# -*- coding: utf-8 -*-
"""切片/检索参数单一变量实验。

链路：管理员切换全局配置 → 实验账号删除旧文档并重新上传（切片参数变更时）→
轮询就绪 → 逐题发起 SSE 问答 → 程序化评分（引用文档命中 + 答案数值命中）。
结果增量写入 experiment/results.json。
"""
import io
import json
import os
import re
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000/api/v1"
HERE = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(HERE, "docs")
RESULTS_PATH = os.path.join(HERE, "results.json")

ENV = dict(re.findall(r"^([A-Z_]+)=(.*)$", open(os.path.join(HERE, "..", ".env"), encoding="utf-8").read(), re.M))
# 实验账号凭据从 backend/.env 读取，不再硬编码在仓库中
EXP_EMAIL = ENV.get("EXP_EMAIL", "exp-lab@outlook.com")
EXP_PASSWORD = ENV.get("EXP_PASSWORD", "")
if not EXP_PASSWORD:
    sys.exit("请在 project/backend/.env 中设置 EXP_PASSWORD（及可选 EXP_EMAIL）后重跑")

client = httpx.Client(timeout=120, trust_env=False)

# ---------- 评测题集：答案全部是文档中的唯一锚点数值 ----------
QUESTIONS = [
    {"q": "量子点蓝光材料 ZnSe-77 器件的外量子效率是多少？", "doc": "量子点", "ans": ["23.7"]},
    {"q": "ZnSe-77 器件的 T95 寿命是多久？", "doc": "量子点", "ans": ["41000"]},
    {"q": "空穴传输层的迁移率提升到了多少？", "doc": "量子点", "ans": ["12.4"]},
    {"q": "量子点面板的量产良率达到多少？", "doc": "量子点", "ans": ["91.3"]},
    {"q": "MoE-X 在 MMLU 上与稠密参考模型的准确率差距缩小到百分之多少？", "doc": "MoE_Survey", "ans": ["3.1"]},
    {"q": "MoE-X 的路由器从多少个候选专家中为每个 token 选择几个？", "doc": "MoE_Survey", "ans": ["64", "top-2"]},
    {"q": "MoE-X 相对稠密基线的每查询能耗降低了百分之多少？", "doc": "MoE_Survey", "ans": ["41"]},
    {"q": "钙钛矿标准配方中 PbI2 与 FAI 的前驱体摩尔比是多少？", "doc": "钙钛矿", "ans": ["1.32"]},
    {"q": "钙钛矿冠军器件的光电转换效率是多少？薄膜在多少摄氏度下退火多久？", "doc": "钙钛矿", "ans": ["25.1", "105"]},
    {"q": "信息检索课程的期末考试占综合成绩的百分之多少？平时作业布置几次？", "doc": "信息检索", "ans": ["40", "3"]},
    {"q": "A 组系统在 GSM8K 测试集上的准确率是多少分？", "doc": "TeamA", "ans": ["88.4"]},
    {"q": "哪一组在 GSM8K 上报告了 84.9 分？该组案例集的一轮解决率是多少？", "doc": "TeamB", "ans": ["84.9", "71.2"]},
]

DOC_FILES = [
    "量子点显示技术报告.pdf",
    "MoE_Survey_2026.txt",
    "钙钛矿薄膜实验记录.docx",
    "信息检索课程讲义.md",
    "TeamA_评测报告.md",
    "TeamB_评测报告.md",
]


def api(tok, method, path, **kw):
    r = client.request(method, f"{BASE}{path}", headers={"Authorization": f"Bearer {tok}"}, **kw)
    data = r.json()
    if data.get("code") != 200:
        raise RuntimeError(f"{method} {path} -> {data}")
    return data["data"]


def login(email, password):
    return api(None, "POST", "/auth/login", json={"email": email, "password": password})["access_token"]


def ensure_exp_user():
    r = client.post(f"{BASE}/auth/register", json={"email": EXP_EMAIL, "password": EXP_PASSWORD})
    body = r.json()
    if body["code"] not in (200, 400):  # 400=已存在
        raise RuntimeError(body)
    print(f"[user] {EXP_EMAIL} ready")


def set_config(admin_tok, **groups):
    api(admin_tok, "PUT", "/admin/configs", json=groups)
    got = api(admin_tok, "GET", "/admin/configs")
    print(f"[config] chunking={got['chunking']} retrieval={got['retrieval']}")
    return got


def delete_all_docs(tok):
    docs = api(tok, "GET", "/docs/list", params={"page": 1, "page_size": 50})["items"]
    for d in docs:
        api(tok, "DELETE", f"/docs/{d['id']}")
    print(f"[docs] deleted {len(docs)} old docs")


def upload_docs(tok):
    files = []
    for fn in DOC_FILES:
        path = os.path.join(DOCS_DIR, fn)
        files.append(("files", (fn, open(path, "rb"), "application/octet-stream")))
    api(tok, "POST", "/docs/upload", files=files)
    deadline = time.time() + 300
    while time.time() < deadline:
        items = api(tok, "GET", "/docs/list", params={"page": 1, "page_size": 50})["items"]
        states = {d["file_name"]: d["status"] for d in items}
        if len(items) == len(DOC_FILES) and all(s == "ready" for s in states.values()):
            print(f"[docs] all {len(items)} ready")
            return items
        if any(s == "failed" for s in states.values()):
            raise RuntimeError(f"parse failed: {states}")
        time.sleep(3)
    raise TimeoutError(f"docs not ready: {states}")


def ask(tok, question, session_id=None):
    """发起一轮 SSE 问答，返回 (session_id, answer, citations, elapsed)。"""
    if session_id is None:
        session_id = api(tok, "POST", "/chat/session")["session_id"]
    start = time.time()
    answer, citations, warnings = [], [], []
    with client.stream(
        "POST",
        f"{BASE}/chat/query",
        headers={"Authorization": f"Bearer {tok}", "Accept": "text/event-stream"},
        json={"session_id": session_id, "query": question, "enable_rag": True},
    ) as resp:
        event, buf = None, []
        for line in resp.iter_lines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                buf.append(line[5:].strip())
            elif not line.strip() and event:
                payload = json.loads("\n".join(buf)) if buf else {}
                if event == "chunk":
                    answer.append(payload.get("content", ""))
                elif event == "done":
                    citations = payload.get("citations") or []
                    warnings = payload.get("warnings") or []
                elif event == "error":
                    raise RuntimeError(f"SSE error: {payload}")
                event, buf = None, []
    return session_id, "".join(answer), citations, warnings, time.time() - start


def score(question, answer, citations, elapsed):
    doc_hit = any(q["doc"] in c["doc_name"] for q in [question] for c in citations)
    ans_hit = all(v in answer for v in question["ans"])
    return {
        "q": question["q"],
        "doc_hit": doc_hit,
        "ans_hit": ans_hit,
        "pass": doc_hit and ans_hit,
        "cited": [f"{c['doc_name'][:18]}#{c['index']}" for c in citations],
        "elapsed": round(elapsed, 1),
        "answer_head": answer[:60].replace("\n", " "),
    }


def load_results():
    if os.path.exists(RESULTS_PATH):
        return json.load(open(RESULTS_PATH, encoding="utf-8"))
    return {}


def save_results(res):
    json.dump(res, open(RESULTS_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def run_round(name, tok, admin_tok, reupload=False, chunking=None, retrieval=None, questions=None):
    res = load_results()
    if name in res and res[name].get("rows") and len(res[name]["rows"]) == len(questions or QUESTIONS):
        print(f"[round] {name} already done, skip")
        return
    if chunking or retrieval:
        set_config(admin_tok, **({"chunking": chunking} if chunking else {}), **({"retrieval": retrieval} if retrieval else {}))
    if reupload:
        delete_all_docs(tok)
        upload_docs(tok)
    rows = []
    for i, q in enumerate(questions or QUESTIONS):
        for attempt in range(3):
            try:
                _, answer, citations, warnings, elapsed = ask(tok, q["q"])
                break
            except Exception as exc:  # 网络/限流重试
                print(f"  retry {i}: {exc}")
                time.sleep(5 * (attempt + 1))
        else:
            rows.append({"q": q["q"], "pass": False, "doc_hit": False, "ans_hit": False, "cited": [], "elapsed": -1, "answer_head": "ERROR"})
            continue
        time.sleep(1)
        row = score(q, answer, citations, elapsed)
        if warnings:
            row["warnings"] = warnings
        rows.append(row)
        print(f"  [{i+1}/{len(questions or QUESTIONS)}] {'PASS' if row['pass'] else 'FAIL'} doc={row['doc_hit']} ans={row['ans_hit']} {row['elapsed']}s")
    n_pass = sum(1 for r in rows if r["pass"])
    avg_t = round(sum(r["elapsed"] for r in rows if r["elapsed"] > 0) / max(1, len(rows)), 1)
    res[name] = {"rows": rows, "pass": n_pass, "total": len(rows), "avg_elapsed": avg_t}
    save_results(res)
    print(f"[round] {name}: {n_pass}/{len(rows)} pass, avg {avg_t}s")
    return res[name]


def summarize():
    res = load_results()
    print(f"\n{'round':<18}{'命中':>8}{'平均耗时':>10}")
    for name, r in res.items():
        if "rows" in r:
            print(f"{name:<18}{r['pass']}/{r['total']:>4}{r['avg_elapsed']:>9}s")


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    admin_tok = login(ENV["INIT_ADMIN_EMAIL"], ENV["INIT_ADMIN_PASSWORD"])
    ensure_exp_user()
    tok = login(EXP_EMAIL, EXP_PASSWORD)

    if stage in ("all", "chunk"):
        # 实验 1 + 2：切片大小与重叠（每组配置重新上传）
        run_round("chunk400_ov60", tok, admin_tok, reupload=True, chunking={"chunk_size": 400, "overlap": 60})
        run_round("chunk600_ov60", tok, admin_tok, reupload=True, chunking={"chunk_size": 600, "overlap": 60})
        run_round("chunk900_ov60", tok, admin_tok, reupload=True, chunking={"chunk_size": 900, "overlap": 60})
        run_round("chunk600_ov0", tok, admin_tok, reupload=True, chunking={"chunk_size": 600, "overlap": 0})
        run_round("chunk600_ov120", tok, admin_tok, reupload=True, chunking={"chunk_size": 600, "overlap": 120})
    if stage in ("all", "topn"):
        # 实验 3：Top-N（查询期参数，复用当前已上传文档，不重传）
        run_round("topn10", tok, admin_tok, retrieval={"top_n": 10, "history_rounds": 5})
        run_round("topn50", tok, admin_tok, retrieval={"top_n": 50, "history_rounds": 5})
        run_round("topn20", tok, admin_tok, retrieval={"top_n": 20, "history_rounds": 5})
    if stage in ("all", "history"):
        # 实验 4：历史轮数（同会话追问场景）
        history_rounds = [
            {"q": "A 组和 B 组系统在 GSM8K 上的准确率分别是多少分？", "doc": "Team", "ans": ["88.4", "84.9"]},
            {"q": "那么哪一组的解题步骤通过率更高？具体是多少？", "doc": "TeamA", "ans": ["94.2"]},
        ]
        for label, rounds in [("hist0", 0), ("hist5", 5)]:
            run_round(label, tok, admin_tok, retrieval={"top_n": 20, "history_rounds": rounds}, questions=history_rounds)
    if stage in ("all", "restore"):
        set_config(admin_tok, chunking={"chunk_size": 600, "overlap": 60}, retrieval={"top_n": 20, "history_rounds": 5})
    summarize()
