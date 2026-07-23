"""
语音测评路由：生成评测文本 + 调用讯飞ISE评测
"""
from fastapi import APIRouter, Query, Request, Depends
from pydantic import BaseModel
from app.utils.xf_ise import assess as xf_assess
from app.utils.qwen_omni import chat_with_audio, chat_text_only
from app.utils.llm_client import chat as llm_chat
from app.utils.auth import current_user
from app.models import voice_assessment as va_db
import random

async def _save_assessment(text, score, accuracy, fluency, integrity, standard, user):
    """后台保存评测记录"""
    if not user:
        return
    va_db.save(user["id"], text, score, accuracy, fluency, integrity, standard)



router = APIRouter(prefix="/api/v1/voice", tags=["Voice"])

# 备用英文短句库，LLM不可用时使用
FALLBACK_SENTENCES = [
    "The weather is beautiful today, let's go for a walk in the park.",
    "I enjoy reading books and learning new things every day.",
    "Technology has changed the way we communicate with each other.",
    "A healthy diet and regular exercise are important for our well-being.",
    "Music can bring people together and lift our spirits.",
    "The library is a quiet place where students can focus on their studies.",
    "Traveling to different countries helps us understand other cultures.",
    "Good morning, how are you doing today?",
    "She has been working very hard to achieve her goals.",
    "The sunset over the ocean was absolutely breathtaking.",
]

# === 口语对练 ===

class ChatReq(BaseModel):
    audio: str | None = None
    text: str | None = None
    history: list | None = None
    voice: str = "Cherry"      # 音色：Cherry/Kai/Eric
    speed: float = 1.0         # 语速：0.8-1.5

@router.post("/chat")
async def voice_chat(req: ChatReq, user: dict = Depends(current_user)):
    """口语对练：发送音频或文本，获取 AI 回复"""
    try:
        if req.audio:
            import base64 as _b64
            audio_data = _b64.b64decode(req.audio)
            result = await chat_with_audio(
                audio_data,
                history=req.history,
                user_text=req.text or "",
                voice=req.voice,
                speed=req.speed
            )
        elif req.text:
            result = await chat_text_only(req.text, history=req.history, voice=req.voice, speed=req.speed)
        else:
            return {"text": "", "history": req.history or [], "error": "请提供音频或文本"}
        
        return {
            "text": result["text"],
            "audio_url": result.get("audio_url", ""),
            "history": result["history"]
        }
    except Exception as e:
        return {
            "text": f"抱歉，出错了: {str(e)[:100]}",
            "history": req.history or [],
            "error": str(e)[:200]
        }


@router.get("/history")
async def get_history(user: dict = Depends(current_user)):
    """获取当前用户的评测历史"""
    return va_db.get_by_user(user["id"])




@router.get("/text")


async def get_text(category: str = Query("daily"), user: dict = None):
    """Generate English evaluation text for the given difficulty."""
    prompts = {
        "ielts": "Generate one or two IELTS Speaking Part 2 style English sentences. Use advanced vocabulary, complex structures, 20-50 words. Return only the sentence, no explanation.",
        "toefl": "Generate one or two TOEFL Speaking style English sentences. Use academic vocabulary, formal tone, 20-50 words. Return only the sentence.",
        "cet4": "Generate one or two CET-4 level English sentences. Use intermediate vocabulary, clear structure, 15-35 words. Return only the sentence.",
        "cet6": "Generate one or two CET-6 level English sentences. Use upper-intermediate vocabulary, moderate complexity, 20-40 words. Return only the sentence.",
        "daily": "Generate one or two daily English conversation sentences. Use common vocabulary, natural tone, 15-35 words. Return only the sentence.",
    }
    system_prompt = prompts.get(category, prompts["daily"])

    try:
        reply = await llm_chat([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Please generate an English reading practice sentence"}
        ])
        text = reply.strip().strip('"').strip("'")
        if 10 < len(text) < 300:
            return {"text": text, "category": category}
    except Exception:
        pass

    return {"text": random.choice(FALLBACK_SENTENCES), "category": category}

    # 兜底
    return {"text": random.choice(FALLBACK_SENTENCES)}


@router.post("/assess")
async def assess_raw(request: Request, user: dict = Depends(current_user)):
    """提交录音进行评测 - JSON 接收 base64 音频"""
    import base64 as _b64, json
    try:
        body = await request.json()
    except:
        return {"score": 0, "comment": "JSON解析失败", "dimensions": []}
    audio_b64 = body.get("audio", "") or body.get("audio_data", "") or ""
    text = body.get("text", "") or body.get("refText", "") or ""
    print(f"REQ: text={repr(text[:100])} audio_len={len(audio_b64) if audio_b64 else 0}", flush=True)
    if not audio_b64:
        return {"score": 0, "comment": f"缺少音频数据", "dimensions": []}
    audio_data = _b64.b64decode(audio_b64)

    if len(audio_data) < 1024:
        return {"score": 0, "comment": "录音文件过小，请重新录制", "dimensions": []}

    if not text or not text.strip():
        text = "The weather is beautiful today."

    try:
        result = await xf_assess(audio_data, text.strip(), category="read_sentence", ent="en_vip")
        print(f"ISE_RESULT: {json.dumps(result, ensure_ascii=False)[:5000]}", flush=True)
        try:
            import asyncio
            dims = result.get("dimensions", [])
            asyncio.create_task(_save_assessment(
                text=text.strip(),
                score=result.get("score", 0),
                accuracy=dims[0].get("score",0) if len(dims)>0 else 0,
                fluency=dims[1].get("score",0) if len(dims)>1 else 0,
                integrity=dims[2].get("score",0) if len(dims)>2 else 0,
                standard=dims[3].get("score",0) if len(dims)>3 else 0,
                user=user
            ))
        except Exception:
            pass
        return result
    except Exception as e:
        return {
            "score": 0,
            "comment": f"评测服务暂时不可用: {str(e)[:100]}",
            "dimensions": [
                {"name": "准确度", "score": 0},
                {"name": "流利度", "score": 0},
                {"name": "完整度", "score": 0},
                {"name": "标准度", "score": 0},
            ],
        }
