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
    question: str = ""         # 当前练习题目（可选）
    character: str = "teacher"  # 对话人物：teacher/friend/examiner/colleague

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
                speed=req.speed,
                question=req.question,
                character=req.character
            )
        elif req.text:
            from app.utils.usage import track, check
            if not check(user, "speak"):
                return {"text": "今日口语对练次数已用完", "history": req.history or []}
            result = await chat_text_only(req.text, history=req.history, voice=req.voice, speed=req.speed, question=req.question, character=req.character)
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




def _clean_units(text: str) -> str:
    """将常见计量单位转为中文，避免 TTS 逐字母拼读。复合优先、单体在后。"""
    import re as _re_unit

    # === 复合单位（优先匹配）===
    text = _re_unit.sub(r"(\d+)\s*km/h", r"\1千米每小时", text)
    text = _re_unit.sub(r"(\d+)\s*m/s", r"\1米每秒", text)
    text = _re_unit.sub(r"(\d+)\s*m/min", r"\1米每分钟", text)
    text = _re_unit.sub(r"(\d+)\s*km\u00b2", r"\1平方千米", text)
    text = _re_unit.sub(r"(\d+)\s*m\u00b2", r"\1平方米", text)
    text = _re_unit.sub(r"(\d+)\s*cm\u00b2", r"\1平方厘米", text)
    text = _re_unit.sub(r"(\d+)\s*mm\u00b2", r"\1平方毫米", text)
    text = _re_unit.sub(r"(\d+)\s*m\u00b3", r"\1立方米", text)
    text = _re_unit.sub(r"(\d+)\s*cm\u00b3", r"\1立方厘米", text)
    text = _re_unit.sub(r"(\d+)\s*dm\u00b3", r"\1立方分米", text)
    text = _re_unit.sub(r"(\d+)\s*g/cm\u00b3", r"\1克每立方厘米", text)
    text = _re_unit.sub(r"(\d+)\s*kg/m\u00b3", r"\1千克每立方米", text)
    text = _re_unit.sub(r"(\d+)\s*mol/L", r"\1摩尔每升", text)
    text = _re_unit.sub(r"(\d+)\s*mmol/L", r"\1毫摩尔每升", text)
    text = _re_unit.sub(r"(\d+)\s*kWh", r"\1千瓦时", text)
    text = _re_unit.sub(r"(\d+)\s*Mbps", r"\1兆比特每秒", text)

    # === 长度 ===
    text = _re_unit.sub(r"(\d+)\s*nm(?![a-zA-Z])", r"\1纳米", text)
    text = _re_unit.sub(r"(\d+)\s*mm(?![a-zA-Z])", r"\1毫米", text)
    text = _re_unit.sub(r"(\d+)\s*cm(?![a-zA-Z])", r"\1厘米", text)
    text = _re_unit.sub(r"(\d+)\s*dm(?![a-zA-Z])", r"\1分米", text)
    text = _re_unit.sub(r"(\d+)\s*km(?![a-zA-Z])", r"\1千米", text)
    text = _re_unit.sub(r"(\d+)\s*m(?![a-zA-Z])", r"\1米", text)

    # === 重量 ===
    text = _re_unit.sub(r"(\d+)\s*t(?![a-zA-Z])", r"\1吨", text)
    text = _re_unit.sub(r"(\d+)\s*kg(?![a-zA-Z])", r"\1千克", text)
    text = _re_unit.sub(r"(\d+)\s*mg(?![a-zA-Z])", r"\1毫克", text)
    text = _re_unit.sub(r"(\d+)\s*g(?![a-zA-Z])", r"\1克", text)

    # === 温度（°C 优先于 °）===
    text = _re_unit.sub(r"(\d+)\s*\u00b0C", r"\1摄氏度", text)
    text = _re_unit.sub(r"(\d+)\s*\u2103", r"\1摄氏度", text)
    text = _re_unit.sub(r"(\d+)\s*\u00b0F", r"\1华氏度", text)
    text = _re_unit.sub(r"(\d+)\s*K(?![a-zA-Z])", r"\1开尔文", text)
    text = _re_unit.sub(r"(\d+)\s*\u00b0(?![CF])", r"\1度", text)

    # === 容积 ===
    text = _re_unit.sub(r"(\d+)\s*mL(?![a-zA-Z])", r"\1毫升", text)
    text = _re_unit.sub(r"(\d+)\s*L(?![a-zA-Z])", r"\1升", text)

    # === 时间 ===
    text = _re_unit.sub(r"(\d+)\s*ms(?![a-zA-Z])", r"\1毫秒", text)
    text = _re_unit.sub(r"(\d+)\s*h(?![a-zA-Z])", r"\1小时", text)
    text = _re_unit.sub(r"(\d+)\s*min(?![a-zA-Z])", r"\1分钟", text)
    text = _re_unit.sub(r"(\d+)\s*s(?![a-zA-Z])", r"\1秒", text)

    # === 电学 ===
    text = _re_unit.sub(r"(\d+)\s*kV(?![a-zA-Z])", r"\1千伏", text)
    text = _re_unit.sub(r"(\d+)\s*mA(?![a-zA-Z])", r"\1毫安", text)
    text = _re_unit.sub(r"(\d+)\s*kW(?![a-zA-Z])", r"\1千瓦", text)
    text = _re_unit.sub(r"(\d+)\s*mAh(?![a-zA-Z])", r"\1毫安时", text)
    text = _re_unit.sub(r"(\d+)\s*GHz(?![a-zA-Z])", r"\1吉赫", text)
    text = _re_unit.sub(r"(\d+)\s*MHz(?![a-zA-Z])", r"\1兆赫", text)
    text = _re_unit.sub(r"(\d+)\s*kHz(?![a-zA-Z])", r"\1千赫", text)
    text = _re_unit.sub(r"(\d+)\s*Hz(?![a-zA-Z])", r"\1赫兹", text)
    text = _re_unit.sub(r"(\d+)\s*V(?![a-zA-Z])", r"\1伏", text)
    text = _re_unit.sub(r"(\d+)\s*A(?![a-zA-Z])", r"\1安", text)
    text = _re_unit.sub(r"(\d+)\s*W(?![a-zA-Z])", r"\1瓦", text)
    text = _re_unit.sub(r"(\d+)\s*\u03a9", r"\1欧姆", text)

    # === 力/压强/能量 ===
    text = _re_unit.sub(r"(\d+)\s*kN(?![a-zA-Z])", r"\1千牛", text)
    text = _re_unit.sub(r"(\d+)\s*kPa(?![a-zA-Z])", r"\1千帕", text)
    text = _re_unit.sub(r"(\d+)\s*MPa(?![a-zA-Z])", r"\1兆帕", text)
    text = _re_unit.sub(r"(\d+)\s*kJ(?![a-zA-Z])", r"\1千焦", text)
    text = _re_unit.sub(r"(\d+)\s*kcal(?![a-zA-Z])", r"\1千卡", text)
    text = _re_unit.sub(r"(\d+)\s*N(?![a-zA-Z])", r"\1牛", text)
    text = _re_unit.sub(r"(\d+)\s*Pa(?![a-zA-Z])", r"\1帕", text)
    text = _re_unit.sub(r"(\d+)\s*J(?![a-zA-Z])", r"\1焦耳", text)
    text = _re_unit.sub(r"(\d+)\s*cal(?![a-zA-Z])", r"\1卡路里", text)

    # === 其他 ===
    text = _re_unit.sub(r"(\d+)\s*mol(?![a-zA-Z])", r"\1摩尔", text)
    text = _re_unit.sub(r"(\d+)\s*dB(?![a-zA-Z])", r"\1分贝", text)

    return text

def _clean_markdown(text: str) -> str:
    """去除 Markdown 格式标记，避免 TTS 读出 * # ` 等符号"""
    import re as _re_md

    # 1. 代码块 ```...``` → 移除
    text = _re_md.sub(r"```[\s\S]*?```", "", text)
    # 行内代码 `...` → 只保留文字
    text = _re_md.sub(r"`([^`]+)`", r"\1", text)

    # 2. 粗体 **text** / __text__ → text
    text = _re_md.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = _re_md.sub(r"__([^_]+)__", r"\1", text)
    # 斜体 *text* / _text_ — 注意不要误伤数学表达式中的 *
    text = _re_md.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", text)
    text = _re_md.sub(r"(?<!_)_([^_]+)_(?!_)", r"\1", text)

    # 3. 删除线 ~~text~~ → text
    text = _re_md.sub(r"~~([^~]+)~~", r"\1", text)

    # 4. 标题 # ## ### → 只保留文字
    text = _re_md.sub(r"^#{1,6}\s*", "", text, flags=_re_md.MULTILINE)

    # 5. 无序列表 - * + → 去掉标记符
    text = _re_md.sub(r"^[\-\*\+]\s+", "", text, flags=_re_md.MULTILINE)

    # 6. 有序列表 1. 2. → 去掉序号
    text = _re_md.sub(r"^\d+\.\s+", "", text, flags=_re_md.MULTILINE)

    # 7. 引用 > → 去掉标记
    text = _re_md.sub(r"^>\s+", "", text, flags=_re_md.MULTILINE)

    # 8. 水平线 --- *** ___ → 去掉整行
    text = _re_md.sub(r"^[\-\*_]{3,}\s*$", "", text, flags=_re_md.MULTILINE)

    # 9. 链接 [text](url) → text (图片已在前面处理)
    text = _re_md.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # 10. 多余空行合并
    text = _re_md.sub(r"\n{3,}", "\n\n", text)

    return text.strip()

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

    # 0. 向量（先处理，避免花括号干扰后续）
    while "\\vec" in text:
        idx = text.find("\\vec")
        if idx + 5 < len(text) and text[idx + 4] == "{":
            end = _match_brace(text, idx + 5)
            inner = text[idx + 5:end]
            text = text[:idx] + "向量" + inner + text[end + 1:]
        else:
            text = text[:idx] + "向量" + text[idx + 4:]
    while "\\overrightarrow" in text:
        idx = text.find("\\overrightarrow")
        brace_start = idx + 15  # len("\\overrightarrow") = 15
        if brace_start < len(text) and text[brace_start] == "{":
            end = _match_brace(text, brace_start + 1)
            inner = text[brace_start + 1:end]
            text = text[:idx] + "向量" + inner + text[end + 1:]
        else:
            text = text[:idx] + "向量" + text[idx + 17:]

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
    # 5b. (x+1)^2 → (x+1)的2次方 (括号后跟上标，括号自身翻译在 7.5 做)
    text = _re_latex.sub(r"([)\]])\^\{([^}]+)\}", r"\1的\2次方", text)
    text = _re_latex.sub(r"([)\]])\^(\d+)", r"\1的\2次方", text)

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

    # 省略号
    text = text.replace("\\ldots", "省略号")
    text = text.replace("\\cdots", "省略号")
    text = text.replace("\\vdots", "省略号")
    text = text.replace("\\ddots", "省略号")

    # 推理符号
    text = text.replace("\\therefore", "所以")
    text = text.replace("\\because", "因为")
    text = text.replace("\\Rightarrow", "推出")
    text = text.replace("\\Leftrightarrow", "等价于")
    text = text.replace("\\rightarrow", "右箭头")

    # 集合/关系
    text = text.replace("\\forall", "任意")
    text = text.replace("\\exists", "存在")
    text = text.replace("\\in", "属于")
    text = text.replace("\\notin", "不属于")
    text = text.replace("\\subset", "包含于")
    text = text.replace("\\subseteq", "包含于等于")
    text = text.replace("\\cup", "并")
    text = text.replace("\\cap", "交")
    text = text.replace("\\emptyset", "空集")

    # 几何
    text = text.replace("\\angle", "角")
    text = text.replace("\\triangle", "三角形")
    text = text.replace("\\parallel", "平行")
    text = text.replace("\\perp", "垂直")
    text = text.replace("\\circ", "度")
    text = text.replace("\\sim", "相似")
    text = text.replace("\\cong", "全等")
    text = text.replace("\\equiv", "恒等")

    # 微积分
    text = text.replace("\\nabla", "梯度")
    text = text.replace("\\partial", "偏导")
    text = text.replace("\\propto", "正比于")

    # 三角函数和数学函数
    text = text.replace("\\sin", "萨茵")
    text = text.replace("\\cos", "口萨茵")
    text = text.replace("\\tan", "探针特")
    text = text.replace("\\cot", "口探针特")
    text = text.replace("\\sec", "塞肯特")
    text = text.replace("\\csc", "口塞肯特")
    text = text.replace("\\arcsin", "阿克萨茵")
    text = text.replace("\\arccos", "阿克口萨茵")
    text = text.replace("\\arctan", "阿克探针特")
    text = text.replace("\\sinh", "双曲萨茵")
    text = text.replace("\\cosh", "双曲口萨茵")
    text = text.replace("\\tanh", "双曲探针特")
    text = text.replace("\\log", "烙格")
    text = text.replace("\\ln", "烙恩")
    text = text.replace("\\lg", "烙格")
    text = text.replace("\\max", "麦克斯")
    text = text.replace("\\min", "敏")
    text = text.replace("\\gcd", "最大公约数")
    text = text.replace("\\lcm", "最小公倍数")

    # 7.5 括号命令：不播报，直接删除（有语义的绝对值/竖线/满足保留）
    # 绝对值配对：\left| x \right| → x的绝对值
    text = _re_latex.sub(r"\\left\|([\s\S]*?)\\right\|", r"\1的绝对值", text)
    # \left \right 系列 → 删除
    text = text.replace("\\left(", "")
    text = text.replace("\\right)", "")
    text = text.replace("\\left[", "")
    text = text.replace("\\right]", "")
    text = text.replace("\\left\\{", "")
    text = text.replace("\\right\\}", "")
    # \big \Big \bigg \Bigg 系列（含 l/r 变体）→ 删除
    for _br in ["\\bigl(", "\\Bigl(", "\\biggl(", "\\Biggl(", "\\big(", "\\Big(", "\\bigg(", "\\Bigg(",
                "\\bigr)", "\\Bigr)", "\\biggr)", "\\Biggr)", "\\big)", "\\Big)", "\\bigg)", "\\Bigg)",
                "\\bigl[", "\\Bigl[", "\\biggl[", "\\Biggl[", "\\big[", "\\Big[", "\\bigg[", "\\Bigg[",
                "\\bigr]", "\\Bigr]", "\\biggr]", "\\Biggr]", "\\big]", "\\Big]", "\\bigg]", "\\Bigg]",
                "\\bigl\\{", "\\Bigl\\{", "\\biggl\\{", "\\Biggl\\{", "\\big\\{", "\\Big\\{", "\\bigg\\{", "\\Bigg\\{",
                "\\bigr\\}", "\\Bigr\\}", "\\biggr\\}", "\\Biggr\\}", "\\big\\}", "\\Big\\}", "\\bigg\\}", "\\Bigg\\}"]:
        text = text.replace(_br, "")
    # 转义花括号（集合 \{1,2,3\}）→ 删除括号
    text = text.replace("\\{", "")
    text = text.replace("\\}", "")
    # 尖括号（内积）→ 删除
    text = text.replace("\\langle", "")
    text = text.replace("\\rangle", "")
    # 取整符号 → 删除
    text = text.replace("\\lfloor", "")
    text = text.replace("\\rfloor", "")
    text = text.replace("\\lceil", "")
    text = text.replace("\\rceil", "")
    # \left \right 后跟未覆盖符号（如 \left\langle）时，删掉残留命令
    text = text.replace("\\left", "")
    text = text.replace("\\right", "")
    # 集合竖线 \mid → 满足（保留语义）
    text = text.replace("\\mid", "满足")
    # 竖线（绝对值/范数）
    text = text.replace("\\lvert", "")
    text = text.replace("\\rvert", "")
    text = text.replace("\\vert", "")
    text = text.replace("\\Vert", "")

    # 7.6 负号翻译：-5 → 负5（前面是数字/字母/右括号时为减法，保留不动）
    # 负号+数字（含小数），如 -5、=-5、-0.5
    text = _re_latex.sub(r"(?<![0-9a-zA-Z)\]\uff09])-(\d+(?:\.\d+)?)", r"负\1", text)
    # 负号+字母/变量，如 -x、-a
    text = _re_latex.sub(r"(?<![0-9a-zA-Z)\]\uff09])-([a-zA-Z])", r"负\1", text)

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

    # 11. 普通 ASCII 括号 → 不播报，删除（\text 等已在上一步清理，此时删括号不影响）
    text = text.replace("(", "")
    text = text.replace(")", "")
    text = text.replace("[", "")
    text = text.replace("]", "")
    text = text.replace("{", "")
    text = text.replace("}", "")

    # 防止连续拼音字母被 TTS 当成英文词读 (mc → "Em Cee")
    text = _re_latex.sub(r"([a-zA-Z])([a-zA-Z])([\u4e00-\u9fff\u7684])", r"\1 \2\3", text)
    return text

def _split_sentences(text: str, max_len: int = 80) -> list:
    """按句切分；返回 [(text, para_end), ...]
    - 相邻短句合并到 max_len 内（默认 80 字，保证句间停顿可控）
    - 遇到段落边界(\n)立即结算当前段，段落不混段，段落间停顿最长
    """
    sent = re.findall(r'[^\u3002\uff01\uff1f.!?\n]+[\u3002\uff01\uff1f.!?\n]*', text.strip())
    if not sent:
        return [(text.strip(), False)]
    out = []
    buf = ""
    for s in sent:
        para_end = s.endswith("\n")
        s = s.strip()
        if not s:
            continue
        if len(buf) + len(s) <= max_len:
            buf += s
        else:
            if buf:
                out.append((buf, False))
            buf = s
        if para_end:
            out.append((buf, True))
            buf = ""
    if buf:
        out.append((buf, False))
    return out


def _pause_ms(s: str, para_end: bool) -> int:
    """根据段末标点/段落边界估算播完后的停顿毫秒数，让语音节奏更自然"""
    if para_end:
        return 500  # 段落结束：最长停顿
    tail = s.strip()
    if not tail:
        return 300
    last = tail[-1]
    if last in "\u3002\uff01\uff1f\u2026":   # 。！？…
        return 400
    if last in ".!?":
        return 500
    if last in "\uff1b;":                        # ；;
        return 350
    if last in "\uff1a:":                        # ：:
        return 300
    if last in "\uff0c,":                        # ，
        return 200
    if last in "\u3001":                         # 、
        return 150
    return 300


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

    clean_text = _clean_latex(_clean_markdown(_clean_units(req.text.strip())))
    sentences = _split_sentences(clean_text, max_len=80)
    segments = []

    for s, para_end in sentences:
        url = await _tts_one(s, req.voice)
        if url:
            segments.append({"text": s, "url": url, "pauseMs": _pause_ms(s, para_end)})
        # 单个句子失败不阻塞整体

    if not segments:
        raise HTTPException(500, "语音合成失败")

    return {"segments": segments}
