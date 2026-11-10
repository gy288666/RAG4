"""Make paired prose answers inspectable without inventing claim annotations."""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.evaluate_literature_answers import dump, sha


def fenced(text):
    marker = "`" * max(3, max((len(m.group()) + 1 for m in re.finditer(r"`+", text)), default=3))
    return f"{marker}text\n{text}\n{marker}"


def export_review(run_dir, output):
    manifest_raw, report_raw = (run_dir / "manifest.json").read_bytes(), (run_dir / "report.json").read_bytes()
    manifest, report = json.loads(manifest_raw), json.loads(report_raw)
    if report["status"] == "running" or report["manifest_sha256"] != sha(manifest_raw):
        raise ValueError("Run unfinished or manifest changed")
    planned, rows = manifest["planned_requests"], report["rows"]
    if len(planned) != 40 or len(rows) != 40:
        raise ValueError("Expected all 40 outcomes, including failures")
    for slot, (request, row) in enumerate(zip(planned, rows)):
        request_sha = sha(json.dumps(request, ensure_ascii=False, sort_keys=True).encode())
        if (row["slot"] != slot or row["request_sha256"] != request_sha
                or (row["question_id"], row["variant"]) != (request["question_id"], request["variant"])):
            raise ValueError("Run row differs from frozen request")
    output.mkdir(parents=True, exist_ok=False)
    annotations = {v: {"schema_version": "literature-answers-v1", "pilot_sha256": manifest["pilot_sha256"],
                       "run_id": sha(report_raw) + ":" + v, "answers": []} for v in ("rag3", "rag4")}
    public_rows = []
    lines = ["# 20题双组答案审阅包", "", "原始模型正文与权威输入来源分开列出。未进行人工评分。",
             "正文中的页码/参考来源由模型生成，应与下方实际输入来源逐项核对。",
             "annotation模板中的null表示未标注，不能直接通过R55校验；不得只保留正确声明。", ""]
    for slot, (request, row) in enumerate(zip(planned, rows)):
        artifact = {"schema_version": "literature-answer-artifact-v1", "manifest_sha256": sha(manifest_raw),
                    "report_sha256": sha(report_raw), "request": request, "outcome": row}
        raw = (json.dumps(artifact, ensure_ascii=False, indent=2) + "\n").encode()
        artifact_sha = sha(raw)
        (output / f"answer-{slot:02}.json").write_bytes(raw)
        public_rows.append({**row, "question": request["messages"][1]["content"],
            "artifact_sha256": artifact_sha,
            "input_evidence": [{k: e[k] for k in ("index", "document_id", "chunk_id", "page")}
                               for e in request["evidence"]]})
        if row["status"] == "succeeded":
            annotations[row["variant"]]["answers"].append({"question_id": row["question_id"],
                "text": row["answer"], "abstained": None, "claims": [],
                "artifact_id": "answer_" + artifact_sha, "artifact_sha256": artifact_sha})
        lines += [f'## {request["question_id"]} / {request["variant"]}', "",
                  fenced(request["messages"][1]["content"]), "", f'状态：{row["status"]}', "",
                  fenced(row["answer"] or "未取得答案；失败/未执行不能补写为成功。"), "", "实际输入来源：", ""]
        for evidence in request["evidence"]:
            lines += [f'[{evidence["index"]}] {evidence["document_id"]}.pdf / PDF第{evidence["page"]}页',
                      "", fenced(evidence["text"]), ""]
    for variant, annotation in annotations.items():
        dump(output / f"{variant}-annotation-pending.json", annotation)
    (output / "review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary = {k: value for k, value in report.items() if k != "rows"}
    summary.update(rows=public_rows, model=manifest["model"], policy=manifest["policy"],
                   provenance={k: manifest[k] for k in ("pilot_sha256", "retrieval_report_sha256",
                       "model_task_sha256", "prompt_sha256", "source_sha256", "executed_source_sha256")},
                   report_sha256=sha(report_raw), annotation_status="pending", held_out_evaluation=False,
                   answer_correctness="unknown", gap_correctness="unknown", limitations=manifest["limitations"])
    dump(output / "summary.json", summary)
    return {"manifest_sha256": sha(manifest_raw), "report_sha256": sha(report_raw),
            "artifacts": len(rows), "annotation_status": "pending",
            "successful_answers": {v: len(a["answers"]) for v, a in annotations.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export_review(args.run, args.output)))


if __name__ == "__main__":
    main()
