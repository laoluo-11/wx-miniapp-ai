"""用户用量追踪 + 限额检查"""
from app.database import get_db
from app.config import (
    USAGE_CHAT_USER, USAGE_CHAT_VIP,
    USAGE_VOICE_USER, USAGE_VOICE_VIP,
    USAGE_SPEAK_USER, USAGE_SPEAK_VIP,
    USAGE_UPLOAD_USER, USAGE_UPLOAD_VIP,
)

LIMITS = {
    "chat":         (USAGE_CHAT_USER,   USAGE_CHAT_VIP),
    "voice_assess": (USAGE_VOICE_USER,  USAGE_VOICE_VIP),
    "speak":        (USAGE_SPEAK_USER,  USAGE_SPEAK_VIP),
    "upload":       (USAGE_UPLOAD_USER, USAGE_UPLOAD_VIP),
}


def get_limit(role: str, metric: str) -> int:
    """获取某角色的某操作限额"""
    limits = LIMITS.get(metric)
    if not limits:
        return 999999
    return limits[1] if role == "vip" else limits[0]


def track(user_id: int, metric: str):
    """记录一次用量"""
    with get_db() as db:
        cur = db.cursor()
        cur.execute("""
            INSERT INTO usage_stats (user_id, metric, date, count)
            VALUES (%s, %s, CURDATE(), 1)
            ON DUPLICATE KEY UPDATE count = count + 1
        """, (user_id, metric))


def check(user: dict, metric: str) -> bool:
    """检查是否超限，返回 True=可继续
    普通用户：累计（总共N次，用完即止）
    VIP用户：每日刷新
    """
    limit = get_limit(user.get("role"), metric)
    is_vip = user.get("role") == "vip"
    with get_db() as db:
        cur = db.cursor()
        if is_vip:
            cur.execute(
                "SELECT count FROM usage_stats WHERE user_id=%s AND metric=%s AND date=CURDATE()",
                (user["id"], metric)
            )
        else:
            cur.execute(
                "SELECT COALESCE(SUM(count), 0) AS count FROM usage_stats WHERE user_id=%s AND metric=%s",
                (user["id"], metric)
            )
        row = cur.fetchone()
        current = int(row["count"]) if row else 0
        return current < limit


def get_today(user_id: int) -> dict:
    """获取当日用量"""
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "SELECT metric, count FROM usage_stats WHERE user_id=%s AND date=CURDATE()",
            (user_id,)
        )
        return {r["metric"]: r["count"] for r in cur.fetchall()}


def get_limits(role: str) -> dict:
    """获取角色所有限额配置（普通用户为累计总次数、VIP为每日刷新）"""
    return {
        "chat":         LIMITS["chat"][1] if role == "vip" else LIMITS["chat"][0],
        "voice_assess": LIMITS["voice_assess"][1] if role == "vip" else LIMITS["voice_assess"][0],
        "speak":        LIMITS["speak"][1] if role == "vip" else LIMITS["speak"][0],
        "upload":       LIMITS["upload"][1] if role == "vip" else LIMITS["upload"][0],
    }
