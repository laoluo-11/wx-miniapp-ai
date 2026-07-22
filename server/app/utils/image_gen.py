"""
图片生成 — 使用 z-image-turbo 模型
"""
import httpx, uuid, os
from app.config import QWEN_API_KEY

DASHSCOPE_URL = "https://ws-vvchkx3qqa728hg2.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

IMAGE_KEYWORDS = ["画", "生成图片", "生成图像", "图片", "generate image", "draw", "create image", "make image", "generate a picture"]


def should_generate_image(text: str) -> bool:
    """检测用户是否要求生成图片"""
    t = text.lower()
    return any(kw in t for kw in IMAGE_KEYWORDS)


async def generate_image(prompt: str, size: str = "1024*1024") -> str | None:
    """生成图片，返回本地静态 URL"""
    payload = {
        "model": "z-image-turbo",
        "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
        "parameters": {"size": size}
    }
    headers = {"Authorization": f"Bearer {QWEN_API_KEY}", "Content-Type": "application/json"}
    
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(DASHSCOPE_URL, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    
    choices = data.get("output", {}).get("choices", [])
    if not choices:
        return None
    
    content = choices[0].get("message", {}).get("content", [])
    image_url = None
    for part in (content if isinstance(content, list) else [content]):
        if isinstance(part, dict) and "image" in part:
            image_url = part["image"]
            break
    
    if not image_url:
        return None
    
    # Download and save locally
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(image_url)
        r.raise_for_status()
        img_data = r.content
    
    ext = ".png"
    name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(UPLOAD_DIR, name)
    with open(path, "wb") as f:
        f.write(img_data)
    
    return f"https://luois-james.xyz/static/{name}"
