"""
学习资料数据层
"""
from app.database import get_db


def add(user_id: int, filename: str, file_url: str, file_size: int = 0) -> int:
    """添加资料记录，返回 id"""
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "INSERT INTO user_materials (user_id,filename,file_url,file_size,status) VALUES (%s,%s,%s,%s,'processing')",
            (user_id, filename, file_url, file_size)
        )
        return cur.lastrowid


def update_status(material_id: int, status: str, chunks_count: int = 0):
    """更新解析状态"""
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "UPDATE user_materials SET status=%s, chunks_count=%s WHERE id=%s",
            (status, chunks_count, material_id)
        )


def list_by_user(user_id: int) -> list:
    """用户资料列表"""
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "SELECT id,filename,file_url,file_size,chunks_count,status,created_at FROM user_materials WHERE user_id=%s ORDER BY created_at DESC",
            (user_id,)
        )
        return cur.fetchall()


def delete(material_id: int, user_id: int) -> bool:
    """删除资料（需同步删除文件 + ChromaDB）"""
    with get_db() as db:
        cur = db.cursor()
        cur.execute("SELECT file_url FROM user_materials WHERE id=%s AND user_id=%s", (material_id, user_id))
        row = cur.fetchone()
        if not row:
            return False
        cur.execute("DELETE FROM user_materials WHERE id=%s AND user_id=%s", (material_id, user_id))
        return True, row["file_url"]
