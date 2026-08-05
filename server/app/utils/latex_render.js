#!/usr/bin/env node
/**
 * LaTeX → SVG 渲染器 (MathJax 3) — 黑底白字
 */
const { mathjax } = require("/opt/node_modules/mathjax-full/js/mathjax.js");
const { TeX } = require("/opt/node_modules/mathjax-full/js/input/tex.js");
const { SVG } = require("/opt/node_modules/mathjax-full/js/output/svg.js");
const { liteAdaptor } = require("/opt/node_modules/mathjax-full/js/adaptors/liteAdaptor.js");
const { RegisterHTMLHandler } = require("/opt/node_modules/mathjax-full/js/handlers/html.js");
const { AllPackages } = require("/opt/node_modules/mathjax-full/js/input/tex/AllPackages.js");

const adaptor = new liteAdaptor();
RegisterHTMLHandler(adaptor);

const tex = new TeX({ packages: AllPackages });
const svgOutput = new SVG({ fontCache: 'local', exFactor: 0.5 });
const doc = mathjax.document('', { InputJax: tex, OutputJax: svgOutput });

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => { input += chunk; });
process.stdin.on("end", () => {
    const formula = input.trim();
    if (!formula) { process.exit(1); }
    try {
        const node = doc.convert(formula, { display: true });
        const svg = adaptor.innerHTML(node);
        // 注入白字样式：覆盖所有 path/text 的 fill 为白色
        const styled = svg.replace(
            /(<svg[^>]*>)/,
            '$1<style>svg path,svg text,svg use{fill:#fff!important;stroke:#fff!important}</style>'
        );
        process.stdout.write(styled);
    } catch (e) {
        process.stderr.write("MathJax error: " + e.message);
        process.exit(1);
    }
});
