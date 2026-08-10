import httpx
from app.config import (
    LLM_API_KEY, LLM_API_BASE, LLM_MODEL, SYSTEM_PROMPT,
    OPENCLAW_URL, OPENCLAW_TOKEN, OPENCLAW_MODEL,
    OPENROUTER_KEY, VISION_MODEL,
    QWEN_API_KEY, QWEN_API_HOST
)
import base64, re

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
QWEN_VL_BASE = f"https://{QWEN_API_HOST}/compatible-mode/v1"
QWEN_VL_MODEL = "qwen3.5-omni-flash"


def _has_image(messages: list) -> bool:
    """检测消息列表中是否包含图片"""
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
    return False


async def _describe_images(messages: list) -> list:
    """用视觉模型描述图片，返回纯文本消息列表"""
    new_messages = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            text_parts = []
            image_urls = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    image_urls.append(part["image_url"]["url"])
                elif isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(part["text"])

            if image_urls:
                text_prompt = " ".join(text_parts) if text_parts else "描述这张图片的内容"
                descriptions = []
                for img_url in image_urls:
                    desc = await _vision_call(img_url, text_prompt)
                    if desc:
                        descriptions.append(desc)
                if descriptions:
                    new_content = "[用户发送了图片] " + " ".join(descriptions)
                    if text_parts:
                        new_content += "\n用户文字: " + " ".join(text_parts)
                    new_messages.append({**msg, "content": new_content})
                    continue
            new_messages.append({**msg, "content": " ".join(text_parts)})
        else:
            new_messages.append(msg)
    return new_messages


async def _vision_call(image_url: str, prompt: str) -> str:
    """Qwen VL 视觉模型描述图片"""
    if not QWEN_API_KEY:
        return ""
    import base64 as _b64
    img_data = image_url
    if image_url.startswith("http"):
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(image_url)
                if r.status_code == 200:
                    img_data = f"data:image/png;base64,{_b64.b64encode(r.content).decode()}"
        except Exception:
            pass
    payload = {
        "model": QWEN_VL_MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": img_data}}
        ]}],
        "max_tokens": 200
    }
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{QWEN_VL_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {QWEN_API_KEY}", "Content-Type": "application/json"},
                json=payload)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            print(f"[Vision] Qwen {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"[Vision] error: {e}")
    return ""

async def _call_llm(messages: list, model: str, system: str,
                    temperature: float, max_tokens: int, timeout: float) -> str:
    """统一 LLM 调用，优先 OpenClaw，fallback 直连 DeepSeek"""
    full = [{"role": "system", "content": system}] + messages
    payload = {
        "model": model, "messages": full,
        "temperature": temperature, "max_tokens": max_tokens
    }

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


async def _call_llm_stream(messages: list, model: str, system: str,
                           temperature: float, max_tokens: int, timeout: float):
    """流式 LLM 调用：逐 token yield"""
    import json as _json
    full = [{"role": "system", "content": system}] + messages
    payload = {
        "model": model, "messages": full,
        "temperature": temperature, "max_tokens": max_tokens,
        "stream": True
    }

    if OPENCLAW_TOKEN:
        headers = {
            "Authorization": f"Bearer {OPENCLAW_TOKEN}",
            "Content-Type": "application/json"
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST",
                    f"{OPENCLAW_URL}/chat/completions",
                    headers=headers, json=payload) as r:
                if r.status_code == 200:
                    async for line in r.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:]
                            if data.strip() == "[DONE]":
                                return
                            try:
                                chunk = _json.loads(data)
                                delta = chunk["choices"][0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                            except Exception:
                                pass
                    return
                print(f"[LLM] OpenClaw stream failed ({r.status_code}), falling back to DeepSeek")

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json"
    }
    use_model = model if model not in (OPENCLAW_MODEL, "openclaw") else LLM_MODEL
    payload["model"] = use_model
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST",
                f"{LLM_API_BASE}/chat/completions",
                headers=headers, json=payload) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        return
                    try:
                        chunk = _json.loads(data)
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except Exception:
                        pass


async def chat(messages: list, uid: int = None, model: str = None, system: str = None) -> str:
    """发送聊天请求。自动检测图片并用视觉模型预处理。"""
    if _has_image(messages) and QWEN_API_KEY:
        messages = await _describe_images(messages)

    system = system or SYSTEM_PROMPT
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


async def gen_title(first_msg: str, uid: int = None, reply: str = None) -> str:
    prompt = first_msg
    if reply:
        prompt = f"用户: {first_msg[:100]}\nAI回复: {reply[:100]}"
    model = LLM_MODEL
    try:
        result = await _call_llm(
            [{"role": "user", "content": prompt}],
            model=model,
            system="根据对话内容，用5-15个字总结为一个标题，直接返回标题不要引号。",
            temperature=0.3, max_tokens=30, timeout=15
        )
        return result.strip()
    except Exception:
        if reply:
            return reply.strip()[:20]
        return first_msg.strip()[:20]


async def chat_stream(messages: list, uid: int = None, model: str = None, system: str = None):
    """流式聊天：逐 token 推送。自动检测图片并用视觉模型预处理。"""
    if _has_image(messages) and QWEN_API_KEY:
        messages = await _describe_images(messages)

    system = system or SYSTEM_PROMPT
    if uid:
        from app.utils.memory_manager import build_context
        ctx = build_context(uid)
        if ctx:
            system = system + ctx

    async for chunk in _call_llm_stream(
        messages,
        model=model or (OPENCLAW_MODEL if OPENCLAW_TOKEN else LLM_MODEL),
        system=system,
        temperature=0.7, max_tokens=2048, timeout=120
    ):
        yield chunk
