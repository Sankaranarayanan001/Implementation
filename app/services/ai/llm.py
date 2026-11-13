"""Qwen3:4b through LangChain + Ollama. Always returns (data, error) – never raises."""
from __future__ import annotations

import json
import re
from functools import lru_cache

from app.core.config import settings


@lru_cache(maxsize=1)
def _client():
    from langchain_ollama import ChatOllama
    return ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=0,
        num_ctx=settings.llm_num_ctx,
        format="json",
        client_kwargs={"timeout": settings.llm_timeout_seconds},
    )


def parse_json(text: str):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        a, b = text.find("{"), text.rfind("}")
        if a != -1 and b > a:
            return json.loads(text[a:b + 1])
        raise


def ask_json(system: str, payload: dict):
    if not settings.llm_enabled:
        return None, "LLM disabled (LLM_ENABLED=false)"
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        msgs = [
            SystemMessage(content=system + "\nRespond with ONE valid JSON object only. /no_think"),
            HumanMessage(content=json.dumps(payload, default=str, ensure_ascii=False)),
        ]
        out = _client().invoke(msgs).content
        data = parse_json(out)
        if not isinstance(data, dict):
            return None, "LLM returned non-object JSON"
        return data, None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"
