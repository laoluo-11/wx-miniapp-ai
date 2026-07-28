"""意图分类器 - 轻量快速判断用户意图，路由到不同处理分支"""

INTENT_CLASSIFIER_PROMPT = """分析用户意图，只返回一行 JSON，不要任何其他文字。

上下文：[CTX: has_file=是/否 has_image=是/否]

意图类型：
1. image - 用户要求画/生成/创作具体实物或动物或场景（非示意图），未上传图片
   {"intent":"image","prompt":"英文描述"}
   prompt 用英文写，详细描述主体、场景、风格、光照

2. diagram - 需要图解辅助：流程图、架构图、几何、物理力学、步骤图、思维导图、对比、时间线
   {"intent":"diagram"}
   上传图片要求据此画示意图也是 diagram

3. analyze - 上传了图片或文件，要求分析、识别、描述、总结
   {"intent":"analyze"}

4. text - 以上都不符合：普通问答、聊天、翻译、计算、写作
   {"intent":"text"}

区分要点：
- 画一个架构图/流程图/示意图 → diagram，不是 image
- 画一只猫/马/人 → image
- 解释勾股定理 配图 → diagram
- 上传照片问这是什么 → analyze
- 你好、翻译这段 → text

输出示例：
{"intent":"image","prompt":"a cute orange tabby cat sitting on a windowsill, soft morning light"}
{"intent":"diagram"}
{"intent":"text"}"""


async def classify_intent(
    text: str,
    has_file: bool = False,
    has_image_file: bool = False
) -> dict:
    """
    快速分类用户意图。直连 DeepSeek，不经过 OpenClaw 网关。
    返回 {"intent": "text"|"image"|"diagram"|"analyze", "prompt": "..."}
    """
    import json as _json
    import httpx
    from app.config import LLM_API_KEY, LLM_API_BASE, LLM_MODEL

    ctx = f"has_file={'是' if has_file else '否'} has_image={'是' if has_image_file else '否'}"
    user_msg = f"[CTX: {ctx}]\n\n{text[:500]}"

    payload = {
        "model": LLM_MODEL or "deepseek-chat",
        "messages": [
            {"role": "system", "content": INTENT_CLASSIFIER_PROMPT},
            {"role": "user", "content": user_msg}
        ],
        "temperature": 0.0,
        "max_tokens": 50
    }
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json"
    }
    base = LLM_API_BASE or "https://api.deepseek.com/v1"

    try:
        async with httpx.AsyncClient(timeout=6) as client:
            r = await client.post(
                f"{base}/chat/completions",
                headers=headers,
                json=payload
            )
            r.raise_for_status()
            result = r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[Intent] API call failed: {e}")
        return {"intent": "text"}

    # Parse JSON response
    try:
        result = result.strip()
        # Remove possible markdown code blocks
        if result.startswith("```"):
            result = result.split("\n", 1)[1] if "\n" in result else result[3:]
            if result.endswith("```"):
                result = result[:-3]
        parsed = _json.loads(result.strip())
        if "intent" not in parsed:
            return {"intent": "text"}
        print(f"[Intent] classified as: {parsed['intent']}")
        return parsed
    except Exception as e:
        print(f"[Intent] JSON parse failed: {e}, raw: {result[:100]}")
        # Fallback: simple keyword matching
        result_lower = result.lower()
        if '"image"' in result_lower or 'image' in result_lower:
            return {"intent": "image", "prompt": text}
        if '"diagram"' in result_lower or 'diagram' in result_lower:
            return {"intent": "diagram"}
        return {"intent": "text"}
