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
Do NOT use markdown formatting in your replies.

IMPORTANT: At the very end of EVERY reply, add a score line in this exact format on its own line:
口语评分：<number>/100
The score (0-100) should reflect the user's pronunciation, fluency, grammar and vocabulary in their latest utterance. Be fair and encouraging, typical range 60-95."""

CHARACTER_PROMPTS = {
    "teacher": """Role: You are a warm, patient English teacher (灵慧老师) helping a student practice spoken English. Follow these rules strictly:
- Speak like a teacher: gentle, encouraging, step-by-step guidance
- When the student makes an error, first praise what they did well, then gently point out the mistake and explain how to fix it (e.g. "很好，但注意这个单词的发音...")
- Use teacher-style expressions: "Good job!", "Let's try again", "Pay attention to the pronunciation of..."
- Simplify your language to the student's level and ask guiding questions
- NEVER be casual or use slang; always maintain a teaching tone""",
    "friend": """Role: You are a close, casual friend chatting with the user. Follow these rules strictly:
- Speak like a friend: relaxed, warm, using everyday conversational language and casual expressions
- Use contractions (I'm, gonna, wanna), light humor, and emoji occasionally
- Share opinions as if chatting casually, ask casual follow-up questions
- Never correct the student's grammar unless they explicitly ask
- Keep the tone light and fun, like chatting over coffee""",
    "examiner": """Role: You are a professional IELTS/TOEFL speaking examiner. Follow these rules strictly:
- Speak formally and professionally, like a real exam setting
- Ask the question directly and objectively without extra warmth
- After the student answers, give a brief professional evaluation: fluency, vocabulary, grammar, pronunciation
- Use exam-style expressions: "Could you tell me more about...?", "Let's move on to the next question"
- Do NOT use emoji or casual language; maintain exam neutrality""",
    "colleague": """Role: You are a professional work colleague in an English-speaking workplace. Follow these rules strictly:
- Speak in business English: polite, professional, efficient
- Use workplace expressions: "Let's schedule a meeting", "Could you follow up on this?", "I'd suggest we..."
- Stay task-oriented and respectful
- If the student uses informal language, gently model the professional alternative
- Keep responses concise and work-related""",
}




async def chat_with_audio(audio_data: bytes, history: list = None, user_text: str = "",
                          voice: str = "Cherry", speed: float = 1.0, question: str = "", character: str = "teacher") -> dict:
    """发送音频到 Qwen-Omni，返回 {'text': ..., 'audio_url': ..., 'history': [...]}"""
    audio_b64 = base64.b64encode(audio_data).decode()
    
    content_parts = [
        {"audio": f"data:;base64,{audio_b64}"},
        {"text": user_text or "请理解我说的话并用英语自然回复"}
    ]
    
    sys_prompt = SYSTEM_PROMPT
    if character in CHARACTER_PROMPTS:
        sys_prompt += f"\n\n{CHARACTER_PROMPTS[character]}"
    if question:
        sys_prompt += f"\n\nCurrent practice question the user is answering: {question}\nGuide the conversation around this question. Ask the question first if the user hasn't answered it yet, then discuss their answer."
    messages = [{"role": "system", "content": [{"text": sys_prompt}]}]
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
                         voice: str = "Cherry", speed: float = 1.0, question: str = "", character: str = "teacher") -> dict:
    """纯文本对话（无音频输入）"""
    sys_prompt = SYSTEM_PROMPT
    if character in CHARACTER_PROMPTS:
        sys_prompt += f"\n\n{CHARACTER_PROMPTS[character]}"
    if question:
        sys_prompt += f"\n\nCurrent practice question the user is answering: {question}\nGuide the conversation around this question. Ask the question first if the user hasn't answered it yet, then discuss their answer."
    messages = [{"role": "system", "content": [{"text": sys_prompt}]}]
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


async def transcribe_audio(audio_data: bytes, language: str = "auto") -> str:
    """语音转文字（ASR）。发送音频到 Qwen-Omni，只要求转写，不回复。"""
    audio_b64 = base64.b64encode(audio_data).decode()

    prompt = "请把这段语音转写成文字，只输出转写结果，不要任何解释或回复。"
    if language == "en":
        prompt = "Transcribe this audio to text. Output ONLY the transcription, no extra words."

    content_parts = [
        {"audio": f"data:;base64,{audio_b64}"},
        {"text": prompt}
    ]
    messages = [{"role": "user", "content": content_parts}]

    headers = {"Authorization": f"Bearer {QWEN_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": QWEN_MODEL, "input": {"messages": messages}}

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(QWEN_DASHSCOPE_URL, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()

    choices = data.get("output", {}).get("choices", [])
    text = ""
    if choices:
        content = choices[0].get("message", {}).get("content", "")
        if isinstance(content, list):
            for part in content:
                text += part.get("text", "") if isinstance(part, dict) else str(part)
        else:
            text = str(content)
    return text.strip()
