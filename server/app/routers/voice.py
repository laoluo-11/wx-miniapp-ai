"""
语音测评路由：生成评测文本 + 调用讯飞ISE评测
"""
from fastapi import APIRouter, Query, Request, Depends, HTTPException
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
FALLBACK_SENTENCES = {
    "ielts": [
        "Climate change represents one of the most significant challenges facing humanity, requiring immediate and coordinated global action.",
        "The rapid advancement of artificial intelligence has fundamentally transformed various sectors of the global economy.",
    ],
    "toefl": [
        "The professor emphasized that critical thinking skills are essential for academic success in higher education.",
        "Researchers have discovered that regular physical exercise can significantly improve cognitive function and memory retention.",
    ],
    "cet4": [
        "Many students find that studying in a quiet environment helps them concentrate better on their assignments.",
        "The Internet has made it much easier for people to access information from all around the world.",
    ],
    "cet6": [
        "The government has implemented a series of measures aimed at reducing carbon emissions across major industries.",
        "Understanding cultural differences is crucial for effective communication in international business settings.",
    ],
    "daily": [
        "The weather is beautiful today, let's go for a walk in the park.",
        "I enjoy reading books and learning new things every day.",
    ],
}

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
            from app.utils.usage import track, check
            if not check(user, "speak"):
                return {"text": "今日口语对练次数已用完", "history": req.history or []}
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
            from app.utils.usage import track, check
            if not check(user, "speak"):
                return {"text": "今日口语对练次数已用完", "history": req.history or []}
            result = await chat_text_only(req.text, history=req.history, voice=req.voice, speed=req.speed)
        else:
            return {"text": "", "history": req.history or [], "error": "请提供音频或文本"}
        
        track(user["id"], "speak")
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
        "ielts": "Generate one English paragraph (about 50 words) for IELTS Speaking Part 2 practice. Use advanced vocabulary and complex structures. IMPORTANT: Output ONLY the paragraph text itself. No greetings, no introductory text, no quotation marks, no extra words. Just the raw paragraph.",
        "toefl": "Generate one English paragraph (about 50 words) for TOEFL Speaking practice. Use academic vocabulary and formal tone. IMPORTANT: Output ONLY the paragraph text itself. No greetings, no introductory text, no quotation marks, no extra words. Just the raw paragraph.",
        "cet4": "Generate one English paragraph (about 50 words) for CET-4 speaking practice. Use intermediate vocabulary and clear structure. IMPORTANT: Output ONLY the paragraph text itself. No greetings, no introductory text, no quotation marks, no extra words. Just the raw paragraph.",
        "cet6": "Generate one English paragraph (about 50 words) for CET-6 speaking practice. Use upper-intermediate vocabulary and moderate complexity. IMPORTANT: Output ONLY the paragraph text itself. No greetings, no introductory text, no quotation marks, no extra words. Just the raw paragraph.",
        "daily": "Generate one English paragraph (about 50 words) for daily conversation practice. Use common vocabulary and natural tone. IMPORTANT: Output ONLY the paragraph text itself. No greetings, no introductory text, no quotation marks, no extra words. Just the raw paragraph.",
    }
    system_prompt = prompts.get(category, prompts["daily"])

    import random as _random
    fallback_list = FALLBACK_SENTENCES.get(category, FALLBACK_SENTENCES["daily"])
    fallback = _random.choice(fallback_list)

    try:
        reply = await llm_chat([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Generate a new sentence, different from: " + fallback}
        ])
        text = reply.strip().strip('"').strip("'")
        # Strip common preambles
        import re as _re2
        text = _re2.sub(r'(?i)^(here\s+is\s+)?(your\s+)?(a\s+)?(english\s+)?(practice\s+)?(speaking\s+)?(paragraph|sentence|text)[:!.]*\s*', '', text).strip()
        if 10 < len(text) < 300:
            return {"text": text, "category": category}
    except Exception:
        pass

    return {"text": fallback, "category": category}

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
        from app.utils.usage import track, check
        if not check(user, "voice_assess"):
            return {"score": 0, "comment": f"今日评测次数已用完", "dimensions": []}
        track(user["id"], "voice_assess")
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

# === TTS 语音播报 ===

import hashlib, os as _os, re

TTS_DIR = _os.path.join(_os.path.dirname(__file__), "..", "..", "..", "uploads", "tts")
_os.makedirs(TTS_DIR, exist_ok=True)


def _match_brace(text: str, start: int) -> int:
    """找到与 text[start-1] 的 { 匹配的 }，返回位置（含）"""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            if depth == 0:
                return i
            depth -= 1
    return len(text) - 1


def _clean_latex(text: str) -> str:
    """将 LaTeX 公式标记转为口语化中文，避免 TTS 读出源码"""
    import re as _re_latex

    # 1. \frac{a}{b} → a分之b (处理嵌套花括号)
    while "\\frac" in text:
        idx = text.find("\\frac")
        if idx + 6 >= len(text) or text[idx + 5] != "{":
            text = text[:idx] + "分数" + text[idx + 5:]
            continue
        num_end = _match_brace(text, idx + 6)
        num = text[idx + 6:num_end]
        denom_start = num_end + 1
        if denom_start >= len(text) or text[denom_start] != "{":
            break
        denom_end = _match_brace(text, denom_start + 1)
        denom = text[denom_start + 1:denom_end]
        text = text[:idx] + denom + "分之" + num + text[denom_end + 1:]

    # 2. \sqrt[n]{x} → x开n次方 (先处理带方括号的)
    text = _re_latex.sub(
        r"\\sqrt\[([^\]]+)\]\{([^}]+)\}", r"\2开\1次方", text
    )
    # 3. \sqrt{x} → 根号x
    text = _re_latex.sub(r"\\sqrt\{([^}]+)\}", r"根号\1", text)

    # 4. x^{n} → x的n次方 (花括号版先)
    text = _re_latex.sub(r"(\w)\^\{([^}]+)\}", r"\1的\2次方", text)
    # 5. x^2 → x的2次方 (裸数字/字母版)
    text = _re_latex.sub(r"(\w)\^(\d+)", r"\1的\2次方", text)

    # 6. x_{n} → x下标n
    text = _re_latex.sub(r"(\w)_\{([^}]+)\}", r"\1下标\2", text)
    # x_1 → x下标1 (无花括号版)
    text = _re_latex.sub(r"(\w)_(\d+)", r"\1下标\2", text)

    # 7. 常见符号命令
    text = text.replace("\\times", "乘")
    text = text.replace("\\div", "除以")
    text = text.replace("\\pm", "正负")
    text = text.replace("\\infty", "无穷大")
    text = text.replace("\\sum", "求和")
    text = text.replace("\\int", "积分")
    text = text.replace("\\lim", "极限")
    text = text.replace("\\to", "趋向于")
    text = text.replace("\\cdot", "乘以")
    text = text.replace("\\neq", "不等于")
    text = text.replace("\\approx", "约等于")
    text = text.replace("\\geq", "大于等于")
    text = text.replace("\\leq", "小于等于")

    # 8. 希腊字母
    text = text.replace("\\alpha", "阿尔法")
    text = text.replace("\\beta", "贝塔")
    text = text.replace("\\gamma", "伽马")
    text = text.replace("\\delta", "德尔塔")
    text = text.replace("\\theta", "西塔")
    text = text.replace("\\lambda", "拉姆达")
    text = text.replace("\\mu", "缪")
    text = text.replace("\\pi", "派")
    text = text.replace("\\sigma", "西格玛")
    text = text.replace("\\omega", "欧米伽")
    text = text.replace("\\epsilon", "伊普西龙")
    text = text.replace("\\varphi", "斐")

    # 9. 去掉 $$ 和 $ 包裹符
    text = _re_latex.sub(r"\$\$([\s\S]*?)\$\$", r"\1", text)
    text = _re_latex.sub(r"(?<!\\)\$([^$]+?)\$", r"\1", text)
    # \( \) 和 \[ \]
    text = _re_latex.sub(r"\\\(([\s\S]*?)\\\)", r"\1", text)
    text = _re_latex.sub(r"\\\[([\s\S]*?)\\\]", r"\1", text)

    # 10. 去掉无语音意义的 LaTeX 命令
    text = _re_latex.sub(r"\\text\{[^}]*\}", "", text)
    text = _re_latex.sub(r"\\mathbf\{([^}]*)\}", r"\1", text)
    text = _re_latex.sub(r"\\mathrm\{([^}]*)\}", r"\1", text)
    text = text.replace("\\displaystyle", "")
    text = text.replace("\\qquad", " ")
    text = text.replace("\\quad", " ")
    text = text.replace("\\,", "")
    text = text.replace("\\!", "")
    text = _re_latex.sub(r"\\\\", "", text)  # line breaks in LaTeX

    # 防止连续拼音字母被 TTS 当成英文词读 (mc → "Em Cee")
    text = _re_latex.sub(r"([a-zA-Z])([a-zA-Z])([\u4e00-\u9fff\u7684])", r"\1 \2\3", text)
    return text

def _split_sentences(text: str, max_len: int = 200) -> list:
    """Split text by sentences, merge short ones up to max_len chars"""
    sent = re.findall(r'[^。！？.!?\n]+[。！？.!?\n]*', text.strip())
    if not sent:
        return [text.strip()]
    out = []
    buf = ""
    for s in sent:
        s = s.strip()
        if not s:
            continue
        if len(buf) + len(s) <= max_len:
            buf += s
        else:
            if buf:
                out.append(buf)
            buf = s
    if buf:
        out.append(buf)
    return out


async def _tts_one(text: str, voice: str = "ruoxi") -> str | None:
    """合成一句话，返回本地静态 URL（Ali TTS 带缓存）"""
    from app.utils.tts_ali import synthesize
    return await synthesize(text, voice=voice)


class TtsReq(BaseModel):
    text: str
    voice: str = "Cherry"  # Cherry / Kai / Eric

@router.post("/tts")
async def tts(req: TtsReq, user: dict = Depends(current_user)):
    """AI 回复语音播报：分段合成，返回 URL 列表"""
    if not req.text or not req.text.strip():
        raise HTTPException(400, "文本为空")

        clean_text = _clean_latex(req.text.strip())
    sentences = _split_sentences(clean_text, max_len=200)
    segments = []

    for s in sentences:
        url = await _tts_one(s, req.voice)
        if url:
            segments.append({"text": s, "url": url})
        # 单个句子失败不阻塞整体

    if not segments:
        raise HTTPException(500, "语音合成失败")

    return {"segments": segments}
