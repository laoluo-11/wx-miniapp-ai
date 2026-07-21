import httpx
from app.config import (
    LLM_API_KEY, LLM_API_BASE, LLM_MODEL, SYSTEM_PROMPT,
    OPENCLAW_URL, OPENCLAW_TOKEN, OPENCLAW_MODEL
)


async def _call_llm(messages: list, model: str, system: str,
                    temperature: float, max_tokens: int, timeout: float) -> str:
    """统一 LLM 调用，优先 OpenClaw，fallback 直连 DeepSeek"""
    full = [{"role": "system", "content": system}] + messages
    payload = {
        "model": model, "messages": full,
        "temperature": temperature, "max_tokens": max_tokens
    }

    # 优先使用 OpenClaw Gateway
    if OPENCLAW_TOKEN:
        headers = {
            "Authorization": f"Bearer {OPENCLAW_TOKEN}",
            "Content-Type": "application/json"
        }
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(
                f"{OPENCLAW_URL}/chat/completions",
                headers=headers, json=payload
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            print(f"[LLM] OpenClaw failed ({r.status_code}), falling back to DeepSeek")

    # Fallback: 直连 DeepSeek
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json"
    }
    payload["model"] = model if model not in (OPENCLAW_MODEL, "openclaw") else LLM_MODEL
    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.post(
            f"{LLM_API_BASE}/chat/completions",
            headers=headers, json=payload
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


async def chat(messages: list, uid: int = None, model: str = None) -> str:
    """发送聊天请求。uid 为空则无记忆注入。"""
    system = SYSTEM_PROMPT
    if uid:
        from app.utils.memory_manager import build_context
        ctx = build_context(uid)
        if ctx:
            system = system + ctx
    return await _call_llm(
        messages,
        model=model or (OPENCLAW_MODEL if OPENCLAW_TOKEN else LLM_MODEL),
        system=system,
        temperature=0.7, max_tokens=2048, timeout=60
    )


async def gen_title(first_msg: str, uid: int = None) -> str:
    model = OPENCLAW_MODEL if OPENCLAW_TOKEN else LLM_MODEL
    result = await _call_llm(
        [{"role": "user", "content": first_msg}],
        model=model,
        system="用5-10个字概括用户意图，只返回标题。",
        temperature=0.3, max_tokens=30, timeout=30
    )
    return result.strip()
