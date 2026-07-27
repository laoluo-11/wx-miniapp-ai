"""
SVG 文件保存（不转 PNG，towxml 直接渲染）
"""
import os, uuid, re

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
    ('\Omega', 'Ω'), ('\omega', 'ω'),
    ('\to', '→'), ('\rightarrow', '→'), ('\leftarrow', '←'), ('\Rightarrow', '⇒'),
    ('\sqrt', '√'), ('\int', '∫'), ('\prod', '∏'),
]


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
    svg = re.sub(r'\$([^$]+)\$', lambda m: _latex_to_unicode(m.group(1)), svg)
    svg = re.sub(r'(\w)_(\d+)', lambda m: m.group(1) + ''.join(_SUB.get(d, d) for d in m.group(2)), svg)
    svg = re.sub(r'(\w)\^(\d+)', lambda m: m.group(1) + ''.join(_SUP.get(d, d) for d in m.group(2)), svg)
    for cmd, uni in [('\cdot', '·'), ('\times', '×'), ('\Omega', 'Ω')]:
        svg = svg.replace(cmd, uni)
    return svg


def svg_save(svg_code: str) -> str | None:
    """保存 SVG 文件，返回静态 URL（不转 PNG）"""
    try:
        svg_code = _convert_text_spans(svg_code)
        # 移除 LLM 可能有问题的 <style> 块
        svg_code = re.sub(r'<style[^>]*>.*?</style>', '', svg_code, flags=re.DOTALL)
        name = f"diagram_{uuid.uuid4().hex[:12]}.svg"
        path = os.path.join(UPLOAD_DIR, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg_code)
        return f"https://yyzhilingweilai.com/static/{name}"
    except Exception as e:
        print(f"[SVG] save failed: {e}")
        return None


# 保留旧函数名兼容（弃用，返回 None 让 chat.py 走新路径）
def svg_to_png(svg_code: str) -> str | None:
    return svg_save(svg_code)
