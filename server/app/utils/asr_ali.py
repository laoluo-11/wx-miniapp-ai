"""
阿里云 NLS 语音识别 (REST 接口)
复用 tts_ali 的 token 管理，比 Qwen-Omni 快 10 倍+
"""
import httpx
from app.utils.tts_ali import _get_token
from app.config import NLS_APPKEY

ASR_URL = "https://nls-gateway.cn-shanghai.aliyuncs.com/stream/v1/asr"

async def recognize(audio_bytes: bytes, fmt: str = "wav", sample_rate: int = 16000) -> str:
    """语音转文字，返回识别文本。失败抛异常"""
    if not audio_bytes:
        raise ValueError("音频数据为空")

    token = await _get_token()
    url = f"{ASR_URL}?appkey={NLS_APPKEY}&format={fmt}&sample_rate={sample_rate}"

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            url,
            headers={
                "X-NLS-Token": token,
                "Content-Type": "application/octet-stream"
            },
            content=audio_bytes
        )
        if r.status_code != 200:
            err = r.text[:200] if r.text else str(r.status_code)
            raise Exception(f"NLS ASR 返回 {r.status_code}: {err}")

        data = r.json()
        result = data.get("result", "").strip()
        if not result:
            raise Exception("NLS ASR 未识别到文字")
        return result
