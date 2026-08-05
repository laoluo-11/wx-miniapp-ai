#!/usr/bin/env node
/**
 * KaTeX → SVG 渲染器
 * 用法: echo "E=mc^2" | node render.js
 * 输出: SVG 字符串到 stdout
 */
const katex = require("/opt/node_modules/katex");

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => { input += chunk; });
process.stdin.on("end", () => {
    const formula = input.trim();
    if (!formula) {
        process.exit(1);
    }
    try {
        const svg = katex.renderToString(formula, {
            throwOnError: false,
            displayMode: true,
            colorIsTextColor: true,  // \color 用 currentColor，适配深色/浅色主题
            trust: true,
        });
        process.stdout.write(svg);
    } catch (e) {
        process.stderr.write("KaTeX error: " + e.message);
        process.exit(1);
    }
});
