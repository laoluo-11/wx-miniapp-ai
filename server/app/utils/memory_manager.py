from app.database import get_db

# 最多保留的活跃记忆条数（超过则触发压缩）
MAX_ACTIVE_MEMORIES = 12
# 上下文预算
SUMMARY_MAX_CHARS = 300
FACTS_MAX_CHARS = 500
TOTAL_BUDGET = 800


def get_all(uid: int, limit: int = 30) -> list:
    """获取用户所有记忆（按重要性+时间排序）"""
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "SELECT id, content, importance, `key`, created_at FROM user_memories"
            " WHERE user_id = %s AND (`key` != '_summary' OR `key` IS NULL) ORDER BY importance DESC, updated_at DESC LIMIT %s",
            (uid, limit)
        )
        return cur.fetchall()


def get_summary(uid: int) -> str:
    """获取用户档案摘要（压缩后的旧记忆）"""
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "SELECT content FROM user_memories WHERE user_id = %s AND `key` = '_summary' LIMIT 1",
            (uid,)
        )
        row = cur.fetchone()
        return row["content"] if row else ""


def _set_summary(uid: int, text: str):
    """保存档案摘要"""
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "SELECT id FROM user_memories WHERE user_id = %s AND `key` = '_summary'",
            (uid,)
        )
        existing = cur.fetchone()
        if existing:
            cur.execute(
                "UPDATE user_memories SET content = %s, updated_at = NOW() WHERE id = %s",
                (text, existing["id"])
            )
        else:
            cur.execute(
                "INSERT INTO user_memories (user_id, `key`, content, importance) VALUES (%s, '_summary', %s, 10)",
                (uid, text)
            )


def add(uid: int, content: str, key: str = None, importance: int = 1) -> int:
    """添加一条记忆"""
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "INSERT INTO user_memories (user_id, `key`, content, importance) VALUES (%s, %s, %s, %s)",
            (uid, key, content, importance)
        )
        return cur.lastrowid


def update_importance(mid: int, delta: int = 1):
    """增减记忆重要度"""
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "UPDATE user_memories SET importance = GREATEST(importance + %s, 1) WHERE id = %s",
            (delta, mid)
        )


def delete(mid: int) -> bool:
    with get_db() as db:
        cur = db.cursor()
        cur.execute("DELETE FROM user_memories WHERE id = %s", (mid,))
        return cur.rowcount > 0


def build_context(uid: int) -> str:
    """构建用户记忆上下文，控制在预算内。
    优先级：摘要 > 高重要度事实 > 近期事实。
    """
    summary = get_summary(uid)
    facts = get_all(uid)

    if not summary and not facts:
        return ""

    parts = ["\n[用户档案]"]
    used = 0

    # 1. 档案摘要（压缩后的旧记忆，始终包含）
    if summary:
        parts.append(summary[:SUMMARY_MAX_CHARS])
        used += len(summary[:SUMMARY_MAX_CHARS])

    # 2. 活跃记忆
    if facts and used < TOTAL_BUDGET:
        parts.append("近期信息:")
        for m in facts:
            line = f"- {m['content']}"
            if used + len(line) > TOTAL_BUDGET:
                break
            parts.append(line)
            used += len(line)

    return "\n".join(parts)


async def maybe_compress(uid: int, llm_call) -> bool:
    """当活跃记忆超过阈值时，将低重要度的旧记忆压缩到摘要。
    返回是否执行了压缩。
    """
    facts = get_all(uid, limit=50)
    if len(facts) <= MAX_ACTIVE_MEMORIES:
        return False

    # 按重要性排序，底部的是待压缩的
    facts.sort(key=lambda m: (m["importance"], m.get("created_at", "")), reverse=True)
    keep = facts[:MAX_ACTIVE_MEMORIES]
    compress = facts[MAX_ACTIVE_MEMORIES:]

    # 用 LLM 将待压缩记忆合成摘要
    old_summary = get_summary(uid)
    items = "\n".join(f"- {m['content']}" for m in compress[:10])
    prompt = f"""将以下零散的用户信息合并为一段简洁的档案摘要（100字以内）。
如果有旧的摘要，和新信息合并更新。

旧摘要: {old_summary or '无'}

新信息:
{items}"""

    try:
        new_summary = await llm_call(
            [{"role": "user", "content": prompt}],
            model=None,
            system="你是一个档案管理助手。用自然的中文将用户信息整理成一段摘要，不要用列表格式。",
            temperature=0.3, max_tokens=150, timeout=25
        )
        new_summary = new_summary.strip()[:SUMMARY_MAX_CHARS]
    except Exception:
        return False

    # 原子操作：保存摘要 + 删除已压缩的记忆
    with get_db() as db:
        _set_summary(uid, new_summary)
        for m in compress:
            db.cursor().execute("DELETE FROM user_memories WHERE id = %s", (m["id"],))
        db.commit()

    print(f"[Memory] 用户 {uid}: {len(compress)} 条记忆已压缩为摘要 ({len(new_summary)} chars)")
    return True
