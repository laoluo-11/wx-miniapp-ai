import sys, asyncio, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 手动加载 .env（避免依赖 pydantic-settings）
from pathlib import Path
env = {}
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=*** line:
            k, v = line.split("=*** 1)
            env[k] = v

import httpx

async def test():
    key = env.get("LLM", "")
    print(f"key_len={len(key)}")
    headers = {"Authorization": f"Bearer ***, "Content-Type": "application/json"}
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": "say OK"}], "max_tokens": 10}
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload)
        data = r.json()
        if "choices" in data:
            print("API_OK:", data["choices"][0]["message"]["content"])
        else:
            print("API_ERR:", str(data)[:200])

asyncio.run(test())
