"""
深度搜索模式：优先 OpenRouter → DeepSeek:online（自带联网搜索）
失败时自动降级为普通 DeepSeek 对话
"""
import httpx, json as _json
from app.config import OPENROUTER_KEY

OR_BASE = "https://openrouter.ai/api/v1"
OR_MODEL = "deepseek/deepseek-chat:online"


async def chat_deep_stream(messages: list, uid=None, system=""):
    """流式深度对话：优先联网搜索，失败降级普通对话"""
    if not OPENROUTER_KEY:
        from app.utils.llm_client import chat_stream
        async for chunk in chat_stream(messages, uid=uid):
            yield chunk
        return

    try:
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
                    raise Exception(f"OpenRouter {r.status_code}: {body[:200]}")

                got_content = False
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
                                got_content = True
                                yield content
                        except Exception:
                            continue

                if not got_content:
                    raise Exception("OpenRouter returned empty response")

    except Exception:
        # OpenRouter 不可用，降级为普通 DeepSeek 对话
        from app.utils.llm_client import chat_stream
        async for chunk in chat_stream(messages, uid=uid):
            yield chunk


async def chat_deep(messages: list, uid=None, system="") -> str:
    """非流式深度对话：优先联网搜索，失败降级普通对话"""
    if not OPENROUTER_KEY:
        from app.utils.llm_client import chat as llm_chat
        return await llm_chat(messages, uid=uid)

    try:
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
                raise Exception(f"OpenRouter {r.status_code}: {r.text[:200]}")

            result = r.json()["choices"][0]["message"].get("content", "")
            if not result:
                raise Exception("OpenRouter returned empty response")
            return result

    except Exception:
        # OpenRouter 不可用，降级为普通 DeepSeek 对话
        from app.utils.llm_client import chat as llm_chat
        return await llm_chat(messages, uid=uid)
