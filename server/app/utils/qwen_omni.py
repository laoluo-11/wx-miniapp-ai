"""
Qwen3.5-Omni 多模态客户端 — 音频输入 → 文本输出
用于口语对练功能
"""
import httpx, base64, json as _json
from app.config import QWEN_API_KEY, QWEN_MODEL

QWEN_DASHSCOPE_URL = "https://ws-vvchkx3qqa728hg2.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

SYSTEM_PROMPT = """You are an English speaking practice partner. Follow these rules:
1. Respond naturally in English, like a real conversation
2. Keep replies concise (1-3 sentences)
3. If the user makes grammar or pronunciation mistakes, gently correct them
4. Adapt to the user's English level
5. Be encouraging and friendly
6. Occasionally ask follow-up questions to keep the conversation going"""


async def chat_with_audio(audio_data: bytes, history: list = None, user_text: str = "", voice: str = "Cherry", speed: float = 1.0) -> dict:
    """发送音频到 Qwen-Omni，返回 {'text': ..., 'history': [...]}
    
    audio_data: PCM 16kHz 16bit mono raw bytes
    history: 之前的对话记录
    """
    audio_b64 = base64.b64encode(audio_data).decode()
    
    content_parts = [
        {"audio": f"data:;base64,{audio_b64}"},
        {"text": user_text or "请理解我说的话并用英语自然回复"}
    ]
    
    messages = [{"role": "system", "content": [{"text": SYSTEM_PROMPT}]}]
    
    if history:
        messages.extend(history)
    
    messages.append({"role": "user", "content": content_parts})
    
    payload = {
        "model": QWEN_MODEL,
        "input": {"messages": messages}
    }
    
    headers = {
        "Authorization": f"Bearer {QWEN_API_KEY}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(QWEN_DASHSCOPE_URL, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    
    output = data.get("output", {})
    choices = output.get("choices", [])
    
    reply_text = ""
    if choices:
        content = choices[0].get("message", {}).get("content", "")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    reply_text += part.get("text", "")
                else:
                    reply_text += str(part)
        else:
            reply_text = str(content)
    
    # Build history for next turn
    new_history = (history or []) + [
        {"role": "user", "content": [{"text": "[用户语音输入]"}]},
        {"role": "assistant", "content": [{"text": reply_text}]}
    ]
    # Keep last 6 rounds
    if len(new_history) > 12:
        new_history = new_history[-12:]
    
    # 调用 TTS 生成语音
    audio_url = ""
    try:
        audio_url = await text_to_speech(reply_text.strip(), voice=voice, speed=speed)
    except Exception:
        pass
    
    return {"text": reply_text.strip(), "audio_url": audio_url, "history": new_history}


async def chat_text_only(text: str, history: list = None, voice: str = "Cherry", speed: float = 1.0) -> dict:
    """纯文本对话（无音频）"""
    messages = [{"role": "system", "content": [{"text": SYSTEM_PROMPT}]}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": [{"text": text}]})
    
    payload = {"model": QWEN_MODEL, "input": {"messages": messages}}
    headers = {"Authorization": f"Bearer {QWEN_API_KEY}", "Content-Type": "application/json"}
    
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
                if isinstance(part, dict):
                    reply_text += part.get("text", "")
        else:
            reply_text = str(content)
    
    new_history = (history or []) + [
        {"role": "user", "content": [{"text": text}]},
        {"role": "assistant", "content": [{"text": reply_text}]}
    ]
    if len(new_history) > 12:
        new_history = new_history[-12:]
    
    # 调用 TTS 生成语音
    audio_url = ""
    try:
        audio_url = await text_to_speech(reply_text.strip(), voice=voice, speed=speed)
    except Exception:
        pass
    
    return {"text": reply_text.strip(), "audio_url": audio_url, "history": new_history}


QWEN_TTS_URL = "https://ws-vvchkx3qqa728hg2.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

async def text_to_speech(text: str, voice: str = "Cherry", speed: float = 1.0) -> str:
    """文字转语音，返回音频 URL"""
    payload = {
        "model": "qwen3-tts-flash",
        "input": {"text": text},
        "parameters": {"voice": voice, "format": "mp3", "speech_rate": speed}
    }
    headers = {
        "Authorization": f"Bearer {QWEN_API_KEY}",
        "Content-Type": "application/json"
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(QWEN_TTS_URL, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        audio = data.get("output", {}).get("audio", {})
        return audio.get("url", "") or audio.get("data", "")
    audio_url = ""
    try:
        audio_url = await text_to_speech(reply_text.strip(), voice=voice, speed=speed)
    except Exception:
        pass
    
    return {"text": reply_text.strip(), "audio_url": audio_url, "history": new_history}
from app.config import QWEN_API_KEY, QWEN_MODEL

QWEN_DASHSCOPE_URL = "https://ws-vvchkx3qqa728hg2.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

SYSTEM_PROMPT = """You are an English speaking practice partner. Follow these rules:
1. Respond naturally in English, like a real conversation
2. Keep replies concise (1-3 sentences)
3. If the user makes grammar or pronunciation mistakes, gently correct them
4. Adapt to the user's English level
5. Be encouraging and friendly
6. Occasionally ask follow-up questions to keep the conversation going"""


async def chat_with_audio(audio_data: bytes, history: list = None, user_text: str = "", voice: str = "Cherry", speed: float = 1.0) -> dict:
    """发送音频到 Qwen-Omni，返回 {'text': ..., 'history': [...]}
    
    audio_data: PCM 16kHz 16bit mono raw bytes
    history: 之前的对话记录
    """
    audio_b64 = base64.b64encode(audio_data).decode()
    
    content_parts = [
        {"audio": f"data:;base64,{audio_b64}"},
        {"text": user_text or "请理解我说的话并用英语自然回复"}
    ]
    
    messages = [{"role": "system", "content": [{"text": SYSTEM_PROMPT}]}]
    
    if history:
        messages.extend(history)
    
    messages.append({"role": "user", "content": content_parts})
    
    payload = {
        "model": QWEN_MODEL,
        "input": {"messages": messages}
    }
    
    headers = {
        "Authorization": f"Bearer {QWEN_API_KEY}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(QWEN_DASHSCOPE_URL, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    
    output = data.get("output", {})
    choices = output.get("choices", [])
    
    reply_text = ""
    if choices:
        content = choices[0].get("message", {}).get("content", "")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    reply_text += part.get("text", "")
                else:
                    reply_text += str(part)
        else:
            reply_text = str(content)
    
    # Build history for next turn
    new_history = (history or []) + [
        {"role": "user", "content": [{"text": "[用户语音输入]"}]},
        {"role": "assistant", "content": [{"text": reply_text}]}
    ]
    # Keep last 6 rounds
    if len(new_history) > 12:
        new_history = new_history[-12:]
    
    # 调用 TTS 生成语音
    audio_url = ""
    try:
        audio_url = await text_to_speech(reply_text.strip(), voice=voice, speed=speed)
    except Exception:
        pass
    
    return {"text": reply_text.strip(), "audio_url": audio_url, "history": new_history}


async def chat_text_only(text: str, history: list = None, voice: str = "Cherry", speed: float = 1.0) -> dict:
    """纯文本对话（无音频）"""
    messages = [{"role": "system", "content": [{"text": SYSTEM_PROMPT}]}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": [{"text": text}]})
    
    payload = {"model": QWEN_MODEL, "input": {"messages": messages}}
    headers = {"Authorization": f"Bearer {QWEN_API_KEY}", "Content-Type": "application/json"}
    
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
                if isinstance(part, dict):
                    reply_text += part.get("text", "")
        else:
            reply_text = str(content)
    
    new_history = (history or []) + [
        {"role": "user", "content": [{"text": text}]},
        {"role": "assistant", "content": [{"text": reply_text}]}
    ]
    if len(new_history) > 12:
        new_history = new_history[-12:]
    
    # 调用 TTS 生成语音
    audio_url = ""
    try:
        audio_url = await text_to_speech(reply_text.strip(), voice=voice, speed=speed)
    except Exception:
        pass
    
    return {"text": reply_text.strip(), "audio_url": audio_url, "history": new_history}


QWEN_TTS_URL = "https://ws-vvchkx3qqa728hg2.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

async def text_to_speech(text: str, voice: str = "Cherry", speed: float = 1.0) -> str:
    """文字转语音，返回音频 URL"""
    payload = {
        "model": "qwen3-tts-flash",
        "input": {"text": text},
        "parameters": {"voice": voice, "format": "mp3", "speech_rate": speed}
    }
    headers = {
        "Authorization": f"Bearer {QWEN_API_KEY}",
        "Content-Type": "application/json"
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(QWEN_TTS_URL, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        audio = data.get("output", {}).get("audio", {})
        return audio.get("url", "") or audio.get("data", "")

