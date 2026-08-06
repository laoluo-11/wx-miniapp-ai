#!/usr/bin/env node
/**
 * MathJax 常驻渲染服务 — HTTP 接口
 * 启动后常驻内存，避免每次 subprocess 冷启动
 * 端口: 9123
 */
const http = require("http");
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

const PORT = 9123;

const server = http.createServer((req, res) => {
    if (req.method !== "POST" || req.url !== "/render") {
        res.writeHead(404);
        res.end("POST /render only");
        return;
    }
    let body = "";
    req.on("data", (chunk) => { body += chunk; });
    req.on("end", () => {
        const formula = body.trim();
        if (!formula) {
            res.writeHead(400);
            res.end("empty formula");
            return;
        }
        try {
            const node = doc.convert(formula, { display: true });
            const svg = adaptor.innerHTML(node);
            const styled = svg.replace(
                /(<svg[^>]*style=")/,
                '$1background:transparent;'
            ).replace(
                /(<svg[^>]*>)/,
                '$1<style>svg *{fill:#fff!important;stroke:#fff!important}svg rect[fill="none"]{fill:none!important}svg line[stroke="none"]{stroke:none!important}</style>'
            );
            res.writeHead(200, { "Content-Type": "image/svg+xml" });
            res.end(styled);
        } catch (e) {
            res.writeHead(500);
            res.end("MathJax error: " + e.message);
        }
    });
});

server.listen(PORT, "127.0.0.1", () => {
    process.stderr.write(`MathJax renderer ready on :${PORT}\n`);
});
