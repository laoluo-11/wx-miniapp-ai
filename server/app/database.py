import pymysql.cursors
from contextlib import contextmanager
from app.config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

def get_conn():
    return pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, database=DB_NAME, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor, autocommit=False)

@contextmanager
def get_db():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
