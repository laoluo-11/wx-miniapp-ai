import httpx, json as _json, asyncio, subprocess, tempfile, os, re
from app.config import OPENCLAW_URL, OPENCLAW_TOKEN, OPENCLAW_MODEL

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the internet for current information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "code_exec",
            "description": "Execute Python code to compute or analyze data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute"}
                },
                "required": ["code"]
            }
        }
    }
]

SYSTEM_EXTRA = (
    "\n\nYou have access to tools: web_search and code_exec. "
    "Use them proactively for factual questions or computation. "
    "After gathering info, provide a complete answer. "
    "For diagrams, use <<<SVG>>>...<<<END>>> or <<<IMAGE>>>...<<<END>>>."
)


async def _web_search(query: str) -> str:
    """Search via DuckDuckGo HTML."""
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if r.status_code != 200:
                return f"Search failed: HTTP {r.status_code}"
            snippets = re.findall(
                r'class="result__snippet[^"]*">(.*?)</a>',
                r.text, re.DOTALL
            )
            results = []
            for s in snippets[:5]:
                clean = re.sub(r'<[^>]+>', '', s).strip()
                if clean:
                    results.append(clean)
            if not results:
                return f"No results for: {query}"
            return "\n\n".join(f"{i+1}. {r}" for i, r in enumerate(results))
    except Exception as e:
        return f"Search error: {str(e)}"


async def _code_exec(code: str) -> str:
    """Execute Python in sandboxed temp dir."""
    try:
        tmpdir = tempfile.mkdtemp(prefix="deep_")
        proc = await asyncio.create_subprocess_exec(
            "python3", "-c", code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=tmpdir
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=30
            )
        except asyncio.TimeoutError:
            proc.kill()
            return "Execution timed out (30s limit)"
        try:
            for f in os.listdir(tmpdir):
                os.remove(os.path.join(tmpdir, f))
            os.rmdir(tmpdir)
        except:
            pass
        out = stdout.decode(errors="replace").strip()
        err = stderr.decode(errors="replace").strip()
        result = out
        if err:
            result += f"\n[stderr]: {err}"
        return result[:3000] or "(no output)"
    except Exception as e:
        return f"Execution error: {str(e)}"


async def chat_deep(messages: list, uid=None, system="", max_turns=5) -> str:
    """Agent mode: LLM with tools, loop until final answer."""
    if not OPENCLAW_TOKEN:
        from app.utils.llm_client import chat as llm_chat
        return await llm_chat(messages, uid=uid)

    full = [{"role": "system", "content": system + SYSTEM_EXTRA}] + messages
    headers = {
        "Authorization": f"Bearer {OPENCLAW_TOKEN}",
        "Content-Type": "application/json"
    }

    for turn in range(max_turns):
        payload = {
            "model": OPENCLAW_MODEL,
            "messages": full,
            "tools": TOOLS,
            "temperature": 0.7,
            "max_tokens": 4096
        }

        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(
                f"{OPENCLAW_URL}/chat/completions",
                headers=headers, json=payload
            )

        if r.status_code != 200:
            raise Exception(f"OpenClaw error: {r.status_code}")

        data = r.json()
        choice = data["choices"][0]
        msg = choice["message"]
        finish = choice.get("finish_reason", "stop")

        if finish == "tool_calls" or msg.get("tool_calls"):
            full.append(msg)
            for tc in msg.get("tool_calls", []):
                fn = tc["function"]
                name = fn["name"]
                args = _json.loads(fn.get("arguments", "{}"))
                print(f"[Deep] tool: {name}({args})")

                if name == "web_search":
                    result = await _web_search(args.get("query", ""))
                elif name == "code_exec":
                    result = await _code_exec(args.get("code", ""))
                else:
                    result = f"Unknown tool: {name}"

                full.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result
                })
            continue

        return msg.get("content", "")

    return "(depth limit reached, please simplify)"
