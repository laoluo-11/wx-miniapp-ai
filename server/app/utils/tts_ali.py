"""
阿里云 NLS 语音合成 (REST 接口)
Token 管理 + MP3 合成 + 本地缓存 + 自动清理
"""
import httpx, json, hashlib, os, time, hmac, uuid, base64, glob
from urllib.parse import urlencode, quote
from app.config import NLS_APPKEY, NLS_AK_ID, NLS_AK_SECRET

TOKEN_URL = "https://nls-meta.cn-shanghai.aliyuncs.com/pop/2018-05-18/tokens"
TTS_URL = "https://nls-gateway.cn-shanghai.aliyuncs.com/stream/v1/tts"

_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "uploads", "tts")
os.makedirs(_CACHE_DIR, exist_ok=True)

_token_cache = {"token": "", "expire": 0}
_last_cleanup = 0
MAX_FILES = 200       # 最多保留文件数
MAX_AGE_DAYS = 7      # 超过 7 天未访问也删除


def _cleanup_tts_cache():
    """清理旧 TTS 缓存：超过 200 个时删最旧的，超过 7 天也删"""
    global _last_cleanup
    now = time.time()
    if now - _last_cleanup < 3600:  # 1 小时内不重复扫描
        return
    _last_cleanup = now

    try:
        files = []
        for f in glob.glob(os.path.join(_CACHE_DIR, "*.mp3")):
            stat = os.stat(f)
            files.append((f, stat.st_mtime, stat.st_atime))

        if not files:
            return

        # 按修改时间排序（旧的在前）
        files.sort(key=lambda x: x[1])

        cutoff = now - MAX_AGE_DAYS * 86400
        removed = 0

        for fpath, mtime, atime in files:
            too_old = (mtime < cutoff and atime < cutoff)
            if removed + len(files) > MAX_FILES or too_old:
                try:
                    os.remove(fpath)
                    removed += 1
                except OSError:
                    pass

        if removed:
            print(f"[TTS] 清理了 {removed} 个旧缓存文件")
    except Exception as e:
        print(f"[TTS] 缓存清理出错: {e}")


def _sign(method: str, params: dict) -> str:
    """阿里云 OpenAPI 签名 (HMAC-SHA1)"""
    sorted_params = sorted(params.items())
    qs = urlencode(sorted_params, quote_via=quote)
    str_to_sign = f"{method}&%2F&{quote(qs, safe='')}"
    key = (NLS_AK_SECRET + "&").encode()
    return base64.b64encode(hmac.new(key, str_to_sign.encode(), hashlib.sha1).digest()).decode()


async def _get_token() -> str:
    """获取 NLS Token（带缓存，24h 有效）"""
    if _token_cache["token"] and time.time() < _token_cache["expire"] - 60:
        return _token_cache["token"]

    params = {
        "AccessKeyId": NLS_AK_ID,
        "Action": "CreateToken",
        "Version": "2019-02-28",
        "Format": "JSON",
        "SignatureMethod": "HMAC-SHA1",
        "SignatureVersion": "1.0",
        "SignatureNonce": uuid.uuid4().hex,
        "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    params["Signature"] = _sign("GET", params)

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(TOKEN_URL, params=params)
        data = r.json()
        tok = data.get("Token", {}).get("Id", "")
        expire = data.get("Token", {}).get("ExpireTime", 0)
        if tok:
            _token_cache["token"] = tok
            _token_cache["expire"] = expire
            return tok
        raise Exception(f"Token fail: {data}")


async def synthesize(text: str, voice: str = "ruoxi") -> str | None:
    """文字转语音，返回本地静态 URL。新合成后自动触发缓存清理"""
    if not text or not text.strip():
        return None
    text = text.strip()

    # MD5 缓存
    key = hashlib.md5(("tts_v2|" + text + voice).encode()).hexdigest()
    cache_path = os.path.join(_CACHE_DIR, f"{key}.mp3")
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 200:
        # 更新访问时间（部分系统 atime 可能被禁用，touch mtime 更可靠）
        try:
            os.utime(cache_path, None)
        except OSError:
            pass
        return f"https://yyzhilingweilai.com/static/tts/{key}.mp3"

    token = await _get_token()
    body = json.dumps({
        "appkey": NLS_APPKEY,
        "token": token,
        "text": text,
        "format": "mp3",
        "sample_rate": 16000,
        "voice": voice,
        "volume": 50,
        "speech_rate": -10,
        "pitch_rate": 5,
    }, ensure_ascii=False)

    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.post(
            TTS_URL,
            headers={"X-NLS-Token": token, "Content-Type": "application/json"},
            content=body,
        )
        if r.status_code == 200 and len(r.content) > 200:
            with open(cache_path, "wb") as f:
                f.write(r.content)
            # 新文件写入后触发清理（5 分钟节流）
            _cleanup_tts_cache()
            return f"https://yyzhilingweilai.com/static/tts/{key}.mp3"
        print(f"[NLS] TTS failed: {r.status_code} {r.content[:200]}")
        return None
