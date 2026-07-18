"""
语音测评路由：生成评测文本 + 调用讯飞ISE评测
"""
from fastapi import APIRouter, Depends, UploadFile, File, Form
from app.utils.auth import current_user
from app.utils.xf_ise import assess as xf_assess
from app.utils.llm_client import chat as llm_chat
import random

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

@router.get("/text")
async def get_text(user: dict = Depends(current_user)):
    """生成一条英语评测文本（随机长度1-2句）"""
    # 尝试用LLM生成
    try:
        reply = await llm_chat([
            {"role": "system", "content": "你是一个英语口语老师。请随机生成一句或两句适合朗读的英语句子，难度适中，长度15-40个单词。只返回句子本身，不要任何解释。"},
            {"role": "user", "content": "请生成一句英语朗读练习句子"}
        ])
        text = reply.strip().strip('"').strip("'")
        if 10 < len(text) < 300:
            return {"text": text}
    except Exception:
        pass
    
    # 兜底
    return {"text": random.choice(FALLBACK_SENTENCES)}


@router.post("/assess")
async def assess(
    audio: UploadFile = File(...),
    text: str = Form(default=""),
    user: dict = Depends(current_user),
):
    """提交录音进行评测"""
    audio_data = await audio.read()
    if len(audio_data) < 1024:
        return {"score": 0, "comment": "录音文件过小，请重新录制", "dimensions": []}
    
    if not text or not text.strip():
        text = "The weather is beautiful today."
    
    try:
        result = await xf_assess(audio_data, text.strip(), category="read_sentence", ent="en_vip")
        return result
    except Exception as e:
        # 讯飞调用失败时返回兜底结果
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
