"""RAG 问答编排（PRD 4.3）。

完整链路：
    历史上下文 → Query Rewrite → 密集检索 (Top-N) → 云端 Rerank (Top-K)
    → 拼接 System Prompt → LLM 流式生成 → 引用溯源 + 持久化

产出的是 ``(event_name, payload)`` 事件流，由 API 层负责编码成 SSE 报文，
使服务层与传输协议解耦。

超时降级 [M-6]：
- Query Rewrite > 3s  → 使用用户原始问题，连接不中断
- Rerank API   > 3s  → 跳过精排，done 帧携带 ``warnings: ["rerank_timeout"]``
- LLM 生成     > 30s → 推送 ``event: error`` 并关闭连接
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Generator, Iterator
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chat import ROLE_ASSISTANT, ROLE_USER, ChatMessage, ChatSession
from app.models.usage_log import EVENT_VECTOR_SEARCH
from app.models.user import User
from app.services import (
    config_service,
    embedding_service,
    llm_service,
    prompts,
    rerank_service,
    usage_service,
)
from app.services.vector_store import RetrievedChunk, get_vector_store
from app.utils.ids import generate_id

logger = logging.getLogger(__name__)

DEFAULT_TITLE = "新对话"
SNIPPET_LENGTH = 220
#: 标题生成超时（秒）；超时即回退为问题前 15 字，不影响问答本身
TITLE_TIMEOUT = 8.0


def new_id(prefix: str) -> str:
    """时间有序 ID，保证同一秒内的消息也能稳定按时序排列。"""
    return generate_id(prefix)


# ------------------------------------------------------------
# 历史上下文
# ------------------------------------------------------------


def load_history(db: Session, session_id: str, rounds: int) -> list[ChatMessage]:
    """读取最近 ``rounds`` 轮（1 轮 = 用户 + 助手两条）对话。"""
    if rounds <= 0:
        return []
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(rounds * 2)
    )
    return list(reversed(db.execute(stmt).scalars().all()))


def _history_as_text(history: list[ChatMessage], limit: int = 600) -> str:
    lines = [
        f"{'用户' if m.role == ROLE_USER else '助手'}：{(m.content or '')[:200]}" for m in history
    ]
    return "\n".join(lines)[-limit:] if lines else "（无历史对话）"


# ------------------------------------------------------------
# 意图路由
# ------------------------------------------------------------

#: 预设快速通道：整条消息（去空白/标点后）完全命中才触发，避免误伤
#: "你好，帮我总结一下文档"这类真实提问。
#: 消息长度超过此值不命中。
_SMALLTALK_MAX_LENGTH = 12
_PUNCTUATION = " \t\r\n，。！？!?,.~～、；;：:\"\"'"

_SMALLTALK_PRESETS: dict[str, str] = {
    "你好": "你好！我是学术知识助手，可以基于你上传的文档回答问题，也可以直接聊学术话题。有什么想问的吗？",
    "您好": "您好！我是学术知识助手，有什么可以帮您？",
    "hi": "Hi！我是学术知识助手，有什么可以帮你？",
    "hello": "Hello！我是学术知识助手，有什么可以帮你？",
    "哈喽": "哈喽！有什么想问的吗？我可以基于你的知识库文档来回答。",
    "在吗": "在的！有什么想问的吗？",
    "在么": "在的！有什么想问的吗？",
    "早上好": "早上好！有什么可以帮你？",
    "下午好": "下午好！有什么可以帮你？",
    "晚上好": "晚上好！有什么可以帮你？",
    "谢谢": "不客气！还有其他问题随时问我。",
    "谢谢你": "不客气！还有其他问题随时问我。",
    "多谢": "不客气！还有其他问题随时问我。",
    "thank you": "You're welcome! Feel free to ask more. ",
    "thanks": "You're welcome!",
    "再见": "再见！随时欢迎回来提问。",
    "拜拜": "拜拜！随时欢迎回来提问。",
    "bye": "Bye! Feel free to come back anytime.",
    "你是谁": "我是这个学术知识引擎的问答助手，基于大语言模型和你上传的知识库文档来回答问题。",
    "你是什么": "我是这个平台接入的大语言模型助手，具体模型由管理员在后台配置。我的特长是结合你上传的文档做检索增强问答。",
    "你叫什么": "我是学术知识助手，你可以叫我小R。有什么文档方面的问题都可以问我。",
    "你叫什么名字": "我是学术知识助手，你可以叫我小R。有什么文档方面的问题都可以问我。",
    "你是啥": "我是学术知识引擎的问答助手，基于大语言模型和你上传的知识库来回答问题。",
    "你是什么东西": "我是学术知识助手，一个大语言模型驱动的问答系统，专门帮你理解上传的文档内容。",
    "你是什么模型": "我是这个平台接入的大语言模型助手，具体模型由管理员在后台配置。我的特长是结合你上传的文档做检索增强问答。",
    "你能做什么": "我可以基于你在知识库里上传的文档回答问题并标注引用来源；关掉「知识库检索」开关后，也可以直接和你讨论学术问题。",
    "你会什么": "我可以基于你上传的文档回答问题并标注引用来源，也可以直接讨论学术问题。",
    "能做什么": "我可以帮你从上传的文档里找信息、回答问题，也可以直接聊学术话题。",
    "你能干嘛": "我可以基于你的知识库文档做检索增强问答，帮你快速找到需要的信息。",
    "你会干嘛": "我会基于你上传的文档回答问题，并标注引用来源。",
    "有什么用": "我可以用大模型结合你上传的知识库来回答问题，让回答更准确、有据可查。",
    "你能干啥": "我可以帮你从文档里找到答案，也可以直接和你讨论问题。试试上传一份文档吧！",
    "你会干啥": "我可以帮你做文档相关的问答，也可以和你聊天讨论问题。",
    "good": "有什么想问的吗？我可以基于你的知识库来回答。",
    "great": "有什么想问的吗？",
    "ok": "好的，有什么想问的吗？",
    "哦": "嗯，有什么想知道的内容吗？",
    "好的": "好的，有什么想问的吗？",
    "行": "好的，有什么可以帮你？",
    "可以": "好的，随时提问！",
    "嗯": "嗯？有什么想问的吗？",
    "没事": "好的，那需要的时候再找我！",
    "没事了": "好的，随时回来！",
    "没有": "好的，那需要的时候再找我。",
    "没什么": "好的，随时欢迎提问。",
}


def match_smalltalk(query: str) -> str | None:
    """命中预设寒暄则返回预设回答，否则返回 None。

    仅做整体匹配（去掉首尾空白与标点、忽略大小写），宁可漏判交给
    路由模型兜底，也不误伤带有真实问题的长消息。
    """
    normalized = query.strip().strip(_PUNCTUATION).lower()
    if not normalized or len(normalized) > _SMALLTALK_MAX_LENGTH:
        return None
    return _SMALLTALK_PRESETS.get(normalized)


def _sse_text(preset: str) -> Generator[str, None, None]:
    """把预设回答拆成 1-3 字的片段流式输出，模拟大模型流式效果。"""
    i = 0
    while i < len(preset):
        # 取 1-3 字一个 chunk（中文以字为单位）
        chunk_size = 1 if i + 1 >= len(preset) else (2 if i + 2 >= len(preset) else 3)
        yield preset[i : i + chunk_size]
        i += chunk_size


def route_and_rewrite(
    query: str,
    history: list[ChatMessage],
    config: config_service.RuntimeConfig,
    *,
    user_id: int,
) -> tuple[bool, str]:
    """一次辅助模型调用同时完成检索路由判断与多轮改写。

    返回 ``(need_retrieval, search_query)``；任何解析或调用失败都降级为
    ``(True, 原始问题)``，保证问答链路永不因路由环节中断 [M-6]。
    """
    prompt = prompts.ROUTE_REWRITE_PROMPT.format(history=_history_as_text(history), query=query)
    try:
        raw = llm_service.complete(
            [{"role": "user", "content": prompt}],
            config,
            user_id=user_id,
            temperature=0.0,
            max_tokens=160,
            timeout=settings.QUERY_REWRITE_TIMEOUT,
            model=config.llm_aux_model,
        )
    except llm_service.LLMError as exc:
        logger.info("检索路由降级（%s），默认执行检索", exc)
        return True, query

    try:
        start, end = raw.index("{"), raw.rindex("}") + 1
        data = json.loads(raw[start:end])
        need_retrieval = bool(data.get("need_retrieval", True))
        rewritten = str(data.get("query") or "").strip().strip('"').strip("「」")
    except (ValueError, TypeError):
        logger.info("检索路由输出非 JSON，默认执行检索: %r", raw[:80])
        return True, query
    return need_retrieval, (rewritten[:200] or query)


# ------------------------------------------------------------
# 检索
# ------------------------------------------------------------


def retrieve(
    query: str, user_id: int, config: config_service.RuntimeConfig
) -> tuple[list[RetrievedChunk], list[str]]:
    """密集检索 Top-N → 云端 Rerank Top-K，返回 ``(片段, 警告)``。"""
    started = time.perf_counter()
    try:
        embedding = embedding_service.embed_query(query, config, user_id=user_id)
        candidates = get_vector_store().search(
            user_id,
            embedding,
            config.retrieval_top_n,
            index_version=config.embedding_version,
        )
    except embedding_service.EmbeddingError as exc:
        usage_service.record(
            event_type=EVENT_VECTOR_SEARCH,
            user_id=user_id,
            duration_ms=int((time.perf_counter() - started) * 1000),
            is_success=False,
            error_message=str(exc),
        )
        raise

    usage_service.record(
        event_type=EVENT_VECTOR_SEARCH,
        user_id=user_id,
        duration_ms=int((time.perf_counter() - started) * 1000),
        is_success=True,
    )

    if not candidates:
        return [], []
    return rerank_service.rerank(query, candidates, config, user_id=user_id)


def build_citations(chunks: list[RetrievedChunk]) -> list[dict[str, Any]]:
    """构造引用列表 [I-3]：PDF 带页码，其余用 chunk_index 表示第 N 个片段。"""
    citations: list[dict[str, Any]] = []
    for i, chunk in enumerate(chunks, start=1):
        snippet = (chunk.text or "").strip().replace("\n", " ")
        citations.append(
            {
                "index": i,
                "doc_id": chunk.doc_id,
                "doc_name": chunk.file_name,
                "page": chunk.page,
                "chunk_index": chunk.chunk_index,
                "snippet": snippet[:SNIPPET_LENGTH],
            }
        )
    return citations


def build_context_prompt(chunks: list[RetrievedChunk]) -> str:
    blocks: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        if chunk.page is not None:
            locator = f"第 {chunk.page} 页"
        else:
            locator = f"第 {chunk.chunk_index + 1} 个片段"
        blocks.append(f"[{i}] 《{chunk.file_name}》—— {locator}\n{chunk.text}")
    return prompts.build_context_block(blocks)


# ------------------------------------------------------------
# 会话标题
# ------------------------------------------------------------


def generate_title(query: str, config: config_service.RuntimeConfig, user_id: int) -> str:
    """基于首轮提问生成 15 字以内的会话标题（PRD 4.4.2）。"""
    fallback = (query or DEFAULT_TITLE).strip().replace("\n", " ")[:15] or DEFAULT_TITLE
    try:
        title = llm_service.complete(
            [{"role": "user", "content": prompts.TITLE_PROMPT.format(query=query[:300])}],
            config,
            user_id=user_id,
            temperature=0.3,
            max_tokens=64,
            timeout=TITLE_TIMEOUT,
            model=config.llm_aux_model,
        )
    except llm_service.LLMError:
        return fallback
    title = (title or "").strip().strip('《》"「」').replace("\n", " ")
    return title[:15] or fallback


# ------------------------------------------------------------
# 主流程
# ------------------------------------------------------------


def stream_answer(
    db: Session,
    user: User,
    session: ChatSession,
    query: str,
    enable_rag: bool = True,
) -> Iterator[tuple[str, dict[str, Any]]]:
    """执行一轮问答，产出 ``(event, data)`` 事件流。

    事件顺序：``chunk``* → [``title``] → ``done``；异常时推送 ``error``。
    """
    config = config_service.load_runtime_config(db)
    warnings: list[str] = []
    citations: list[dict[str, Any]] = []

    history = load_history(db, session.id, config.history_rounds)
    is_first_round = len(history) == 0

    # 用户提问先落库，保证异常时消息不丢失
    user_message = ChatMessage(
        id=new_id("msg"), session_id=session.id, role=ROLE_USER, content=query, citations=None
    )
    db.add(user_message)
    db.commit()

    # ---------- 意图路由 ----------
    use_rag = enable_rag
    if use_rag:
        # 第一层：预设寒暄快速通道，零模型调用、即时逐字流式返回
        preset = match_smalltalk(query)
        if preset is not None:
            for part in _sse_text(preset):
                yield "chunk", {"content": part}
            if is_first_round:
                session.title = query.strip()[:15] or DEFAULT_TITLE
                db.add(session)
                db.commit()
                yield "title", {"session_id": session.id, "title": session.title}
            message_id = _persist_assistant_message(db, session, preset, [], False)
            yield "done", {"message_id": message_id, "citations": [], "warnings": []}
            return

    # ---------- 检索阶段 ----------
    search_query = query
    if use_rag:
        # 先看历史里有没有多轮追问需要改写（只有历史存在时才调用）
        if history:
            try:
                rewritten = llm_service.complete(
                    [{"role": "user", "content": prompts.QUERY_REWRITE_PROMPT.format(
                        history=_history_as_text(history), query=query)}],
                    config, user_id=user.id, temperature=0.0, max_tokens=120,
                    timeout=settings.QUERY_REWRITE_TIMEOUT, model=config.llm_aux_model,
                )
                search_query = rewritten.strip().strip('"').strip("「」")[:200] or query
            except llm_service.LLMError:
                search_query = query

    if use_rag:
        try:
            chunks, warnings = retrieve(search_query, user.id, config)
            citations = build_citations(chunks)
            context_prompt = build_context_prompt(chunks)
        except embedding_service.EmbeddingError as exc:
            yield "error", {"code": 500, "message": str(exc)}
            return
        system_prompt = prompts.RAG_SYSTEM_PROMPT.format(retrieved_contexts=context_prompt)
    else:
        # [S-4] 纯模型对话：跳过检索与精排，仍保留多轮上下文
        system_prompt = prompts.PLAIN_SYSTEM_PROMPT

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for message in history:
        messages.append({"role": message.role, "content": message.content or ""})
    messages.append({"role": "user", "content": query})

    # ---------- 流式生成 ----------
    answer_parts: list[str] = []
    try:
        for piece in llm_service.stream_chat(messages, config, user_id=user.id):
            answer_parts.append(piece)
            yield "chunk", {"content": piece}
    except llm_service.LLMTimeoutError:
        _persist_assistant_message(db, session, "".join(answer_parts), citations, use_rag)
        yield "error", {"code": 500, "message": "大模型生成超时（超过 30 秒），请稍后重试"}
        return
    except llm_service.LLMError as exc:
        yield "error", {"code": 500, "message": str(exc)}
        return

    answer = "".join(answer_parts).strip()
    if not answer:
        # 推理型模型可能把输出预算全部消耗在思考内容上而不产出正文。
        # 此时不落库空消息，直接告知用户重试，避免界面出现空白气泡。
        logger.warning("大模型未产出任何正文内容: session=%s", session.id)
        yield "error", {"code": 500, "message": "大模型未返回有效内容，请重试或在后台更换模型"}
        return

    # ---------- 首轮标题 ----------
    # 必须在主回答流结束之后再生成：与主流并发调用同一个 API Key 时，
    # 服务商的并发/频率限制会拖慢甚至中断主回答流（实测出现过回答被截断）。
    # api_document 4.6.1 允许标题在"文本传输期间或即将结束时"推送，故此处合规。
    if is_first_round:
        title = generate_title(query, config, user.id)
        if title:
            session.title = title
            db.add(session)
            db.commit()
            yield "title", {"session_id": session.id, "title": title}

    # ---------- 持久化与 done 帧 ----------
    message_id = _persist_assistant_message(db, session, answer, citations, use_rag)

    yield "done", {
        "message_id": message_id,
        # [S-4] enable_rag=false 时 citations 为空数组
        "citations": citations if use_rag else [],
        "warnings": warnings if use_rag else [],
    }


def _persist_assistant_message(
    db: Session,
    session: ChatSession,
    answer: str,
    citations: list[dict[str, Any]],
    enable_rag: bool,
) -> str:
    message = ChatMessage(
        id=new_id("msg"),
        session_id=session.id,
        role=ROLE_ASSISTANT,
        content=answer or "（未生成任何内容）",
        # [S-4] 纯模型对话模式下 citations 字段存 NULL
        citations=(citations or None) if enable_rag else None,
    )
    db.add(message)
    # 触发会话 updated_at 更新，使侧边栏按最近活跃排序
    session.updated_at = datetime.now()
    db.add(session)
    db.commit()
    return message.id
