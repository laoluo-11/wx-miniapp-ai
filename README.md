# ZLWL 智聆未来 - AI 伴学助手后端

> 全科 AI 伴学微信小程序后端服务
> 技术栈：FastAPI + MariaDB + DeepSeek/OpenClaw + 讯飞 ISE + 千问

## 项目简介

ZLWL（智领未来）是一款全科 AI 伴学微信小程序的后端服务，提供：

- **AI 智能聊天**：多会话、流式输出、意图分类、SVG 示意图、AI 创意图片生成
- **口语测评**：讯飞 ISE 多难度英语口语评分
- **口语对练**：Qwen-Omni 语音对话
- **会员系统**：VIP 角色 + 用量限额 + 管理后台
- **文件管理**：用户上传文件、AI 生成图片统一入库

## 快速开始

```bash
# 安装依赖
cd server
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env   # 填入 DeepSeek/微信/讯飞等密钥

# 启动服务
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 4
```

## 目录结构

```
server/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置加载 (.env)
│   ├── database.py          # MariaDB 连接
│   ├── routers/             # 路由
│   │   ├── auth.py          # 微信登录
│   │   ├── chat.py          # AI 对话/文件/记忆
│   │   ├── user.py          # 用户资料/手机号绑定
│   │   ├── voice.py         # 口语测评/对练
│   │   ├── admin.py         # 管理后台 API
│   │   └── latex_proxy.py   # LaTeX 渲染代理
│   ├── models/              # 数据库模型
│   ├── utils/
│   │   ├── llm_client.py    # LLM 调用 (OpenClaw→DeepSeek fallback)
│   │   ├── intent.py        # 意图分类器
│   │   ├── deep_agent.py    # 深度模式 (工具调用)
│   │   ├── image_gen.py     # 千问生图
│   │   ├── svg_render.py    # SVG 保存
│   │   ├── diagram_prompt.py# 配图 system prompt
│   │   ├── xf_ise.py        # 讯飞 ISE
│   │   └── usage.py         # 用量追踪
├── admin/                   # 管理后台 HTML
└── requirements.txt
```

## 核心架构

```
用户消息 → intent.py 意图分类
  ├─ image   → 千问 qwen-image-max 直接生图
  ├─ diagram → LLM 文字 + SVG 示意图
  ├─ analyze → LLM 分析上传文件
  └─ text    → LLM 纯文字回复

LLM 调用链：OpenClaw 网关 (工具调用) → 失败降级 DeepSeek
```

## 环境变量 (server/.env)

| 变量 | 说明 |
|------|------|
| `WX_APPID` / `WX_SECRET` | 微信小程序凭证 |
| `LLM_API_KEY` / `LLM_BASE` / `LLM_MODEL` | DeepSeek 配置 |
| `OPENCLAW_URL` / `OPENCLAW_TOKEN` | OpenClaw 网关 |
| `QWEN_API_KEY` | 千问生图/Omni |
| `XF_API_KEY` / `XF_API_SECRET` | 讯飞 ISE |
| `DB_*` | MariaDB 连接 |
| `ADMIN_PASSWORD` | 管理后台密码 |
| `USE_INTENT_CLASSIFIER` | 意图分类开关 (true/false) |

## 管理后台

- 地址：`/admin`（经 Nginx 代理）
- 功能：用户 CRUD、VIP 管理、用量查看、对话/文件/记忆管理

## 相关文档

- [API.md](API.md) — 接口文档
- [DEVELOP.md](DEVELOP.md) — 开发日志
- [项目总结.md](项目总结.md) — 项目总结
- [voice-dev-log.md](voice-dev-log.md) — 语音功能开发日志

## 部署

- 服务器：阿里云 ECS (2C/3.7G, Alibaba Cloud Linux 4)
- 域名：yyzhilingweilai.com（ICP 备案：皖ICP备2026022605号-1）
- Nginx 反向代理 8000 端口，Let's Encrypt 证书
