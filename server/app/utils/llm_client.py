import httpx
from app.config import (
    LLM_API_KEY, LLM_API_BASE, LLM_MODEL, SYSTEM_PROMPT,
    OPENCLAW_URL, OPENCLAW_TOKEN, OPENCLAW_MODEL,
    OPENROUTER_KEY, VISION_MODEL
)
import base64, re

OPENROUTER_BASE = "https://openrouter.ai/api/v1"


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
    """调用 OpenRouter 视觉模型描述图片"""
    if not OPENROUTER_KEY:
        return ""
    payload = {
        "model": VISION_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_url}}
            ]
        }],
        "max_tokens": 200
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{OPENROUTER_BASE}/chat/completions",
                headers=headers, json=payload
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            print(f"[Vision] OpenRouter returned {r.status_code}")
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


async def chat(messages: list, uid: int = None, model: str = None) -> str:
    """发送聊天请求。自动检测图片并用视觉模型预处理。"""
    if _has_image(messages) and OPENROUTER_KEY:
        messages = await _describe_images(messages)

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


async def chat_stream(messages: list, uid: int = None, model: str = None):
    """流式聊天：逐 token 推送。自动检测图片并用视觉模型预处理。"""
    if _has_image(messages) and OPENROUTER_KEY:
        messages = await _describe_images(messages)

    system = SYSTEM_PROMPT
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
