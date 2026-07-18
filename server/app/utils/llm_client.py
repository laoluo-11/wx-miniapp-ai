import httpx
from app.config import LLM_API_KEY, LLM_API_BASE, LLM_MODEL, SYSTEM_PROMPT

async def chat(messages: list, model: str = None) -> str:
    headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
    full = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
    payload = {"model": model or LLM_MODEL, "messages": full, "temperature": 0.7, "max_tokens": 2048}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{LLM_API_BASE}/chat/completions", headers=headers, json=payload)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

async def gen_title(first_msg: str) -> str:
    headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": LLM_MODEL, "messages": [
        {"role": "system", "content": "用5-10个字概括用户意图，只返回标题。"},
        {"role": "user", "content": first_msg}
    ], "temperature": 0.3, "max_tokens": 30}
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{LLM_API_BASE}/chat/completions", headers=headers, json=payload)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
