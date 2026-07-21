from app.database import get_db

def get_user_stats(uid: int) -> dict:
    return {'total_conversations': 0, 'total_messages': 0}
