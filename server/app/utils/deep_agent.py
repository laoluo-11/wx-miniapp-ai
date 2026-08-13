"""
联网搜索模式：阿里云百炼 qwen-max + enable_search（服务端自动联网）
失败时自动降级为普通对话
"""
import httpx, json as _json
from app.config import QWEN_API_KEY, QWEN_BASE_URL

WEB_SEARCH_MODEL = "qwen-max"


def _normalize_latex(text: str) -> str:
    """qwen 输出 LaTeX 原生语法 \\(...\\) \\[...\\]，转成 markdown $...$ $$...$$ 供前端 towxml 渲染"""
    if not text:
        return text
    text = text.replace("\\(", "$").replace("\\)", "$")
    text = text.replace("\\[", "$$").replace("\\]", "$$")
    return text


async def chat_deep_stream(messages: list, uid=None, system=""):
    """流式联网搜索：qwen-max + enable_search，失败降级普通对话"""
    if not QWEN_API_KEY:
        from app.utils.llm_client import chat_stream
        async for chunk in chat_stream(messages, uid=uid, system=system):
            yield chunk
        return

    try:
        full = [{"role": "system", "content": system}] + messages
        payload = {
            "model": WEB_SEARCH_MODEL,
            "messages": full,
            "temperature": 0.7,
            "max_tokens": 4096,
            "stream": True,
            "enable_search": True
        }
        headers = {
            "Authorization": f"Bearer {QWEN_API_KEY}",
            "Content-Type": "application/json"
        }

        pending = ""  # 跨 chunk 残留的孤立反斜杠（可能是 \\( \\) \\[ \\] 被切断）
        async with httpx.AsyncClient(timeout=300) as c:
            async with c.stream("POST", f"{QWEN_BASE_URL}/chat/completions",
                                headers=headers, json=payload) as r:
                if r.status_code != 200:
                    body = await r.aread()
                    raise Exception(f"Qwen {r.status_code}: {body[:200]}")

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
                                content = pending + content
                                # 末尾是孤立反斜杠：可能是 \( 或 \) 等被切断，留到下个 chunk
                                if content.endswith("\\"):
                                    pending = "\\"
                                    content = content[:-1]
                                else:
                                    pending = ""
                                if content:
                                    got_content = True
                                    yield _normalize_latex(content)
                        except Exception:
                            continue

                # flush 残留
                if pending:
                    yield _normalize_latex(pending)

                if not got_content and not pending:
                    raise Exception("Qwen returned empty response")

    except Exception:
        # qwen-max 不可用，降级为普通对话
        from app.utils.llm_client import chat_stream
        async for chunk in chat_stream(messages, uid=uid, system=system):
            yield chunk


async def chat_deep(messages: list, uid=None, system="") -> str:
    """非流式联网搜索：qwen-max + enable_search，失败降级普通对话"""
    if not QWEN_API_KEY:
        from app.utils.llm_client import chat as llm_chat
        return await llm_chat(messages, uid=uid, system=system)

    try:
        payload = {
            "model": WEB_SEARCH_MODEL,
            "messages": [{"role": "system", "content": system}] + messages,
            "temperature": 0.7,
            "max_tokens": 4096,
            "enable_search": True
        }
        headers = {
            "Authorization": f"Bearer {QWEN_API_KEY}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=300) as c:
            r = await c.post(f"{QWEN_BASE_URL}/chat/completions", headers=headers, json=payload)
            if r.status_code != 200:
                raise Exception(f"Qwen {r.status_code}: {r.text[:200]}")

            result = r.json()["choices"][0]["message"].get("content", "")
            if not result:
                raise Exception("Qwen returned empty response")
            return _normalize_latex(result)

    except Exception:
        # qwen-max 不可用，降级为普通对话
        from app.utils.llm_client import chat as llm_chat
        return await llm_chat(messages, uid=uid, system=system)
