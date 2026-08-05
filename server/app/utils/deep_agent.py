"""
深度搜索模式：OpenRouter → DeepSeek:online（自带联网搜索）
搜索结果自动注入上下文，无需本地工具循环
"""
import httpx, json as _json
from app.config import OPENROUTER_KEY

OR_BASE = "https://openrouter.ai/api/v1"
OR_MODEL = "deepseek/deepseek-chat:online"


async def chat_deep_stream(messages: list, uid=None, system=""):
    """流式深度对话：DeepSeek + 联网搜索，搜索结果融入回复"""
    if not OPENROUTER_KEY:
        from app.utils.llm_client import chat_stream
        async for chunk in chat_stream(messages, uid=uid):
            yield chunk
        return

    full = [{"role": "system", "content": system}] + messages
    payload = {
        "model": OR_MODEL,
        "messages": full,
        "temperature": 0.7,
        "max_tokens": 4096,
        "stream": True
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=120) as c:
        async with c.stream("POST", f"{OR_BASE}/chat/completions",
                            headers=headers, json=payload) as r:
            if r.status_code != 200:
                body = await r.aread()
                raise Exception(f"OpenRouter error {r.status_code}: {body[:300]}")
            async for line in r.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = _json.loads(data)
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except Exception:
                        continue


async def chat_deep(messages: list, uid=None, system="") -> str:
    """非流式深度对话"""
    if not OPENROUTER_KEY:
        from app.utils.llm_client import chat as llm_chat
        return await llm_chat(messages, uid=uid)

    payload = {
        "model": OR_MODEL,
        "messages": [{"role": "system", "content": system}] + messages,
        "temperature": 0.7,
        "max_tokens": 4096
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{OR_BASE}/chat/completions", headers=headers, json=payload)
        if r.status_code != 200:
            raise Exception(f"OpenRouter error {r.status_code}: {r.text[:300]}")
        return r.json()["choices"][0]["message"].get("content", "")
