"""
Qwen3.5-Omni 多模态客户端 — 音频输入 → 文本 + 语音输出
用于口语对练功能
"""
import httpx, base64, json as _json
from app.config import QWEN_API_KEY, QWEN_MODEL

QWEN_DASHSCOPE_URL = "https://ws-vvchkx3qqa728hg2.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
QWEN_TTS_URL = QWEN_DASHSCOPE_URL

SYSTEM_PROMPT = """You are a friendly English speaking practice partner. 

Your role:
- Have natural, flowing conversations in English
- Keep replies concise (1-3 sentences) so TTS playback is quick
- Gently correct grammar or pronunciation mistakes when you notice them
- Adapt to the user's English level — use simpler words for beginners
- Be encouraging and positive
- Ask follow-up questions to keep the conversation going
- Occasionally use emoji to make the chat feel warm

Remember: the user is learning English, so speak clearly and naturally.
Do NOT use markdown formatting in your replies."""


async def chat_with_audio(audio_data: bytes, history: list = None, user_text: str = "",
                          voice: str = "Cherry", speed: float = 1.0) -> dict:
    """发送音频到 Qwen-Omni，返回 {'text': ..., 'audio_url': ..., 'history': [...]}"""
    audio_b64 = base64.b64encode(audio_data).decode()
    
    content_parts = [
        {"audio": f"data:;base64,{audio_b64}"},
        {"text": user_text or "请理解我说的话并用英语自然回复"}
    ]
    
    messages = [{"role": "system", "content": [{"text": SYSTEM_PROMPT}]}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": content_parts})
    
    headers = {"Authorization": f"Bearer {QWEN_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": QWEN_MODEL, "input": {"messages": messages}}
    
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(QWEN_DASHSCOPE_URL, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    
    choices = data.get("output", {}).get("choices", [])
    reply_text = ""
    if choices:
        content = choices[0].get("message", {}).get("content", "")
        if isinstance(content, list):
            for part in content:
                reply_text += part.get("text", "") if isinstance(part, dict) else str(part)
        else:
            reply_text = str(content)
    
    new_history = (history or []) + [
        {"role": "user", "content": [{"text": "[用户语音输入]"}]},
        {"role": "assistant", "content": [{"text": reply_text}]}
    ]
    if len(new_history) > 12:
        new_history = new_history[-12:]
    
    audio_url = ""
    try:
        audio_url = await text_to_speech(reply_text.strip(), voice=voice, speed=speed)
    except Exception:
        pass
    
    return {"text": reply_text.strip(), "audio_url": audio_url, "history": new_history}


async def chat_text_only(text: str, history: list = None,
                         voice: str = "Cherry", speed: float = 1.0) -> dict:
    """纯文本对话（无音频输入）"""
    messages = [{"role": "system", "content": [{"text": SYSTEM_PROMPT}]}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": [{"text": text}]})
    
    headers = {"Authorization": f"Bearer {QWEN_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": QWEN_MODEL, "input": {"messages": messages}}
    
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(QWEN_DASHSCOPE_URL, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    
    choices = data.get("output", {}).get("choices", [])
    reply_text = ""
    if choices:
        content = choices[0].get("message", {}).get("content", "")
        if isinstance(content, list):
            for part in content:
                reply_text += part.get("text", "") if isinstance(part, dict) else str(part)
        else:
            reply_text = str(content)
    
    new_history = (history or []) + [
        {"role": "user", "content": [{"text": text}]},
        {"role": "assistant", "content": [{"text": reply_text}]}
    ]
    if len(new_history) > 12:
        new_history = new_history[-12:]
    
    audio_url = ""
    try:
        audio_url = await text_to_speech(reply_text.strip(), voice=voice, speed=speed)
    except Exception:
        pass
    
    return {"text": reply_text.strip(), "audio_url": audio_url, "history": new_history}


async def text_to_speech(text: str, voice: str = "Cherry", speed: float = 1.0) -> str:
    """文字转语音，返回音频 URL"""
    payload = {
        "model": "qwen3-tts-flash",
        "input": {"text": text},
        "parameters": {"voice": voice, "format": "mp3", "speech_rate": speed}
    }
    headers = {"Authorization": f"Bearer {QWEN_API_KEY}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(QWEN_TTS_URL, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        audio = data.get("output", {}).get("audio", {})
        return audio.get("url", "") or audio.get("data", "")
