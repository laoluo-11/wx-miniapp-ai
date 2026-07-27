import os
from dotenv import load_dotenv
from pathlib import Path

env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    load_dotenv(env_file)
else:
    load_dotenv()

WX_APPID = os.getenv("WX_APPID", "")
WX_SECRET = os.getenv("WX_SECRET", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "miniapp")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "wx_miniapp")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_API_BASE = os.getenv("LLM_BASE", "https://api.deepseek.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
# OpenClaw Gateway
OPENCLAW_URL = os.getenv("OPENCLAW_URL", "http://127.0.0.1:12178/v1")
OPENCLAW_TOKEN = os.getenv("OPENCLAW_TOKEN", "")
OPENCLAW_MODEL = os.getenv("OPENCLAW_MODEL", "openclaw")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY", "")
VISION_MODEL = os.getenv("VISION_MODEL", "qwen/qwen3-vl-235b-a22b-instruct")
SYSTEM_PROMPT = os.getenv("SYSPROMPT", "你是一个友好的AI助手。")
MAX_HISTORY = int(os.getenv("MAX_HIST", "10"))
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8080"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
XF_API_KEY = os.getenv("XF_API_KEY", "")
XF_API_SECRET = os.getenv("XF_API_SECRET", "")
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_API_HOST = os.getenv("QWEN_API_HOST", "")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "")
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen3-omini")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123456")
