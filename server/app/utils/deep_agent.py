import httpx, json as _json, asyncio, subprocess, tempfile, os, re
from app.config import OPENCLAW_URL, OPENCLAW_TOKEN, OPENCLAW_MODEL

SYSTEM_TOOLS = """
You have access to these tools. To use a tool, output exactly one JSON object per line:
{"tool":"web_search","query":"your search query"}
{"tool":"code_exec","code":"python code to run"}

After tool results come back, continue your answer. You may use multiple tools.
For diagrams, use <<<SVG>>>...<<<END>>> or <<<IMAGE>>>...<<<END>>>.
"""


async def _web_search(query: str) -> str:
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
                clean = re.sub(r"<[^>]+>", "", s).strip()
                if clean:
                    results.append(clean)
            if results:
                return "\n\n".join(f"{i+1}. {r}" for i, r in enumerate(results))
            return f"No results for: {query}"
    except Exception as e:
        return f"Search error: {str(e)}"


async def _code_exec(code: str) -> str:
    try:
        tmpdir = tempfile.mkdtemp(prefix="dp_")
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
            return "Execution timed out (30s)"
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




async def chat_deep_stream(messages: list, uid=None, system="", max_turns=5):
    '''流式深度对话：逐 chunk 输出，遇工具调用暂停执行后继续'''
    if not OPENCLAW_TOKEN:
        from app.utils.llm_client import chat_stream
        async for chunk in chat_stream(messages, uid=uid):
            yield chunk
        return

    full = [{"role": "system", "content": system + SYSTEM_TOOLS}] + messages
    headers = {
        "Authorization": f"Bearer {OPENCLAW_TOKEN}",
        "Content-Type": "application/json"
    }

    for turn in range(max_turns):
        payload = {
            "model": OPENCLAW_MODEL,
            "messages": full,
            "temperature": 0.7,
            "max_tokens": 4096,
            "stream": True
        }

        full_content = ""
        async with httpx.AsyncClient(timeout=120) as c:
            async with c.stream("POST", f"{OPENCLAW_URL}/chat/completions",
                                headers=headers, json=payload) as r:
                if r.status_code != 200:
                    raise Exception(f"OpenClaw error: {r.status_code}")
                async for line in r.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = _json.loads(data)
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_content += content
                                yield content
                        except Exception:
                            continue

        # Check for tool calls in the complete response
        tool_re = re.compile(
            r'^\s*\{\s*"tool"\s*:\s*"(\w+)"\s*,\s*(.+?)\}\s*$',
            re.MULTILINE
        )
        tool_calls = list(tool_re.finditer(full_content))

        if not tool_calls:
            return

        # Execute tools
        results = []
        for m in tool_calls:
            tool_name = m.group(1)
            try:
                args = _json.loads("{" + m.group(2) + "}")
            except Exception:
                continue

            if tool_name == "web_search":
                result_text = await _web_search(args.get("query", ""))
            elif tool_name == "code_exec":
                result_text = await _code_exec(args.get("code", ""))
            else:
                result_text = f"Unknown tool: {tool_name}"

            results.append(f"Tool {tool_name}: {result_text[:500]}")

        # Add tool results to message history
        full.append({"role": "assistant", "content": full_content})
        full.append({"role": "user", "content": f"Tool results:\n" + "\n".join(results)})


async def chat_deep(messages: list, uid=None, system="", max_turns=5) -> str:
    if not OPENCLAW_TOKEN:
        from app.utils.llm_client import chat as llm_chat
        return await llm_chat(messages, uid=uid)

    full = [{"role": "system", "content": system + SYSTEM_TOOLS}] + messages
    headers = {
        "Authorization": f"Bearer {OPENCLAW_TOKEN}",
        "Content-Type": "application/json"
    }

    for turn in range(max_turns):
        payload = {
            "model": OPENCLAW_MODEL,
            "messages": full,
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

        content = r.json()["choices"][0]["message"]["content"]

        # Parse tool calls: JSON lines with "tool" key
        tool_re = re.compile(
            r'^\s*\{\s*"tool"\s*:\s*"(\w+)"\s*,\s*(.+?)\}\s*$',
            re.MULTILINE
        )
        tool_calls = list(tool_re.finditer(content))

        if not tool_calls:
            return content

        # Execute tools
        results = []
        for m in tool_calls:
            tool_name = m.group(1)
            try:
                args = _json.loads("{" + m.group(2) + "}")
            except:
                continue

            print(f"[Deep] tool: {tool_name}({args})")
            if tool_name == "web_search":
                result = await _web_search(args.get("query", ""))
            elif tool_name == "code_exec":
                result = await _code_exec(args.get("code", ""))
            else:
                result = f"Unknown tool: {tool_name}"
            results.append(f"[{tool_name}]\n{result}")

        # Clean content and continue
        clean = tool_re.sub("", content).strip()
        full.append({"role": "assistant", "content": clean or "Using tools..."})
        full.append({"role": "user", "content": "Tool results:\n" + "\n\n".join(results) + "\n\nContinue your answer."})

    return "(depth limit reached, please simplify)"