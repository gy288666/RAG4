"""LLM 调用服务（OpenAI 兼容接口）。

对应 PRD 5.3 模型层抽象：管理员在后台切换 Base URL / API Key / Model 即可
接入 DeepSeek、通义千问、OpenAI 或本地自建模型，无需修改代码。

``DEV_MOCK_AI=true`` 时启用本地 Mock 生成，便于离线联调与自动化测试。
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator

import httpx

from app.core.config import settings
from app.models.usage_log import EVENT_LLM_CALL
from app.services import usage_service
from app.services.config_service import RuntimeConfig
from app.services.embedding_service import build_endpoint

logger = logging.getLogger(__name__)

#: 单次问答的最大输出 Token 数（含推理型模型的思考内容）
MAX_OUTPUT_TOKENS = 4096


class LLMError(RuntimeError):
    """LLM 调用失败。"""


class LLMTimeoutError(LLMError):
    """LLM 调用超时（PRD 4.3.3 [M-6]：生成超时 > 30s）。"""


def estimate_tokens(text: str) -> int:
    """粗略估算 Token 数：中文约 1 字 1 token，英文约 4 字符 1 token。"""
    if not text:
        return 0
    chinese = sum(1 for ch in text if "一" <= ch <= "鿿")
    return chinese + max(0, (len(text) - chinese)) // 4


def _headers(config: RuntimeConfig) -> dict[str, str]:
    if not config.llm_api_key:
        raise LLMError("尚未配置大模型 API Key，请联系管理员在后台完成配置")
    return {
        "Authorization": f"Bearer {config.llm_api_key}",
        "Content-Type": "application/json",
    }


# ------------------------------------------------------------
# 离线 Mock
# ------------------------------------------------------------


def _mock_answer(messages: list[dict[str, str]]) -> str:
    question = ""
    for message in reversed(messages):
        if message.get("role") == "user":
            question = message.get("content", "")
            break
    has_context = any("【背景资料】" in (m.get("content") or "") for m in messages)
    if has_context:
        return (
            f"根据检索到的背景资料，关于「{question[:40]}」的要点如下 [1]：\n"
            "该结论直接来自所提供的文献片段，未作任何推测性补充 [1]。"
        )
    return f"（离线演示模式）你的问题是：{question[:80]}。当前未接入真实大模型服务。"


def _mock_stream(messages: list[dict[str, str]]) -> Iterator[str]:
    text = _mock_answer(messages)
    step = 8
    for i in range(0, len(text), step):
        yield text[i : i + step]


# ------------------------------------------------------------
# 对外接口
# ------------------------------------------------------------


def stream_chat(
    messages: list[dict[str, str]],
    config: RuntimeConfig,
    *,
    user_id: int | None = None,
    temperature: float = 0.2,
    timeout: float | None = None,
) -> Iterator[str]:
    """流式生成，逐段 yield 增量文本。

    调用结束（正常或异常）后写入 ``usage_logs`` 的 ``llm_call`` 记录。
    """
    timeout = timeout or settings.LLM_TIMEOUT
    started = time.perf_counter()
    prompt_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)
    output_chars: list[str] = []

    if settings.DEV_MOCK_AI:
        for piece in _mock_stream(messages):
            output_chars.append(piece)
            yield piece
        usage_service.record(
            event_type=EVENT_LLM_CALL,
            user_id=user_id,
            tokens_used=prompt_tokens + estimate_tokens("".join(output_chars)),
            duration_ms=int((time.perf_counter() - started) * 1000),
            is_success=True,
        )
        return

    endpoint = build_endpoint(config.llm_base_url, "chat/completions")
    payload = {
        "model": config.llm_model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
        # 必须显式给足输出预算：推理型模型（如 DeepSeek-V4-Flash）会先产出
        # reasoning_content 思考内容，同样计入 max_tokens。若沿用服务商默认值
        # （常见为 512），思考过程就会吃掉预算，导致正文被截断甚至为空。
        "max_tokens": MAX_OUTPUT_TOKENS,
    }
    reported_tokens: int | None = None

    try:
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
            with client.stream(
                "POST", endpoint, headers=_headers(config), json=payload
            ) as response:
                if response.status_code >= 400:
                    response.read()
                    raise LLMError(
                        f"大模型服务返回错误（HTTP {response.status_code}），请检查模型配置"
                    )
                for line in response.iter_lines():
                    if not line:
                        continue
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        parsed = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if usage := parsed.get("usage"):
                        reported_tokens = int(usage.get("total_tokens") or 0) or reported_tokens
                    for choice in parsed.get("choices") or []:
                        piece = (choice.get("delta") or {}).get("content")
                        if piece:
                            output_chars.append(piece)
                            yield piece
    except httpx.TimeoutException as exc:
        usage_service.record(
            event_type=EVENT_LLM_CALL,
            user_id=user_id,
            duration_ms=int((time.perf_counter() - started) * 1000),
            is_success=False,
            error_message="LLM 生成超时",
        )
        raise LLMTimeoutError("大模型生成超时，请稍后重试") from exc
    except LLMError:
        usage_service.record(
            event_type=EVENT_LLM_CALL,
            user_id=user_id,
            duration_ms=int((time.perf_counter() - started) * 1000),
            is_success=False,
            error_message="LLM 调用失败",
        )
        raise
    except httpx.HTTPError as exc:
        usage_service.record(
            event_type=EVENT_LLM_CALL,
            user_id=user_id,
            duration_ms=int((time.perf_counter() - started) * 1000),
            is_success=False,
            error_message=str(exc),
        )
        raise LLMError(f"大模型服务调用失败：{exc}") from exc

    usage_service.record(
        event_type=EVENT_LLM_CALL,
        user_id=user_id,
        tokens_used=reported_tokens or (prompt_tokens + estimate_tokens("".join(output_chars))),
        duration_ms=int((time.perf_counter() - started) * 1000),
        is_success=True,
    )


def complete(
    messages: list[dict[str, str]],
    config: RuntimeConfig,
    *,
    user_id: int | None = None,
    temperature: float = 0.2,
    max_tokens: int = 256,
    timeout: float | None = None,
    model: str | None = None,
) -> str:
    """非流式生成，用于问题改写与会话标题生成等短任务。

    ``model`` 留空时使用主模型；调用方可传入后台配置的辅助小模型，
    避免推理型主模型的思考耗时把这类短任务拖超时。
    """
    timeout = timeout or settings.LLM_TIMEOUT
    started = time.perf_counter()

    if settings.DEV_MOCK_AI:
        answer = _mock_answer(messages)[:max_tokens]
        usage_service.record(
            event_type=EVENT_LLM_CALL,
            user_id=user_id,
            tokens_used=estimate_tokens(answer),
            duration_ms=int((time.perf_counter() - started) * 1000),
            is_success=True,
        )
        return answer

    endpoint = build_endpoint(config.llm_base_url, "chat/completions")
    payload = {
        "model": model or config.llm_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    try:
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=5.0)) as client:
            response = client.post(endpoint, headers=_headers(config), json=payload)
            response.raise_for_status()
            body = response.json()
    except httpx.TimeoutException as exc:
        usage_service.record(
            event_type=EVENT_LLM_CALL,
            user_id=user_id,
            duration_ms=int((time.perf_counter() - started) * 1000),
            is_success=False,
            error_message="LLM 调用超时",
        )
        raise LLMTimeoutError("大模型调用超时") from exc
    except (httpx.HTTPError, ValueError) as exc:
        usage_service.record(
            event_type=EVENT_LLM_CALL,
            user_id=user_id,
            duration_ms=int((time.perf_counter() - started) * 1000),
            is_success=False,
            error_message=str(exc),
        )
        raise LLMError(f"大模型服务调用失败：{exc}") from exc

    content = ""
    for choice in body.get("choices") or []:
        content = (choice.get("message") or {}).get("content") or ""
        break

    usage = body.get("usage") or {}
    usage_service.record(
        event_type=EVENT_LLM_CALL,
        user_id=user_id,
        tokens_used=int(usage.get("total_tokens") or estimate_tokens(content)),
        duration_ms=int((time.perf_counter() - started) * 1000),
        is_success=True,
    )
    return content.strip()
