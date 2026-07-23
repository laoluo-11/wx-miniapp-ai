"""
SVG -> PNG rendering (server-side)
"""
import os, uuid, re, cairosvg

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

_SUB = {'0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄', '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉'}
_SUP = {'0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹'}
_LATEX_CMDS = [
    ('\cdot', '·'), ('\neq', '≠'), ('\sum', '∑'), ('\times', '×'), ('\div', '÷'),
    ('\pm', '±'), ('\infty', '∞'), ('\angle', '∠'), ('\triangle', '△'), ('\cong', '≅'),
    ('\approx', '≈'), ('\leq', '≤'), ('\geq', '≥'), ('\parallel', '∥'), ('\perp', '⊥'),
    ('\alpha', 'α'), ('\beta', 'β'), ('\pi', 'π'), ('\theta', 'θ'), ('\mu', 'μ'),
    ('\sigma', 'σ'), ('\lambda', 'λ'), ('\gamma', 'γ'), ('\delta', 'δ'), ('\Delta', 'Δ'),
    ('\to', '→'), ('\rightarrow', '→'), ('\leftarrow', '←'), ('\Rightarrow', '⇒'),
    ('\sqrt', '√'), ('\int', '∫'), ('\prod', '∏'),
    ('\Omega', 'Ω'), ('\omega', 'ω'),
]

# No forced font-family - let cairo use system fontconfig fallback
# Fonts installed: Noto Sans CJK SC, Noto Sans Math, Noto Sans Symbols


def _latex_to_unicode(math: str) -> str:
    r = math
    for cmd, uni in _LATEX_CMDS:
        r = r.replace(cmd, uni)
    r = re.sub(r'(\w)\^\{([^}]+)\}', lambda m: m.group(1) + ''.join(_SUP.get(c, c) for c in m.group(2)), r)
    r = re.sub(r'(\w)\^(\d+)', lambda m: m.group(1) + ''.join(_SUP.get(d, d) for d in m.group(2)), r)
    r = re.sub(r'(\w)_\{([^}]+)\}', lambda m: m.group(1) + ''.join(_SUB.get(c, c) for c in m.group(2)), r)
    r = re.sub(r'(\w)_(\d+)', lambda m: m.group(1) + ''.join(_SUB.get(d, d) for d in m.group(2)), r)
    r = r.replace('\\{', '{').replace('\\}', '}')
    r = r.replace('\\', '')
    return r


def _convert_text_spans(svg: str) -> str:
    """Convert bare LaTeX-style sub/superscripts and $...$ math in SVG text content."""
    # 1. Convert $...$ blocks
    svg = re.sub(r'\$([^$]+)\$', lambda m: _latex_to_unicode(m.group(1)), svg)
    # 2. Convert bare subscripts (word_number) within text elements
    svg = re.sub(r'(\w)_(\d+)', lambda m: m.group(1) + ''.join(_SUB.get(d, d) for d in m.group(2)), svg)
    # 3. Convert bare superscripts
    svg = re.sub(r'(\w)\^(\d+)', lambda m: m.group(1) + ''.join(_SUP.get(d, d) for d in m.group(2)), svg)
    # 4. Convert common LaTeX commands outside $...$
    for cmd, uni in [('\cdot', '·'), ('\times', '×'), ('\Omega', 'Ω')]:
        svg = svg.replace(cmd, uni)
    return svg


def _preprocess_svg(svg: str) -> str:
    svg = _convert_text_spans(svg)
    # Remove LLM's <style> blocks (may have incomplete fonts) and let system defaults handle it
    svg = re.sub(r'<style[^>]*>.*?</style>', '', svg, flags=re.DOTALL)
    return svg


def svg_to_png(svg_code: str) -> str | None:
    try:
        # Debug: log raw SVG input
        with open("/tmp/last_svg_input.svg", "w") as _f:
            _f.write(svg_code)
        svg_code = _preprocess_svg(svg_code)
        with open("/tmp/last_svg_processed.svg", "w") as _f:
            _f.write(svg_code)
        name = f"diagram_{uuid.uuid4().hex[:12]}.png"
        path = os.path.join(UPLOAD_DIR, name)
        cairosvg.svg2png(bytestring=svg_code.encode("utf-8"), write_to=path)
        return f"https://luois-james.xyz/static/{name}"
    except Exception as e:
        print(f"[SVG] render failed: {e}")
        return None
