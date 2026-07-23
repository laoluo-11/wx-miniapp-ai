# ZLWL 智能聊天 — 开发文档

> 最后更新：2026-07-22

## 项目概述

ZLWL（智聆未来）是一个英语口语学习微信小程序，核心功能包括 AI 智能聊天和语音评测。用户可与 AI 自由对话、上传文件让 AI 分析，还能录音进行英语口语发音评测。

## 系统架构

```
                    微信小程序 (wxb81645ad7e110063)
                            │
                  HTTPS (luois-james.xyz)
                            │
                     Cloudflare CDN
                      (橙色云朵代理)
                            │
                   Cloudflare Tunnel
                  (626935f4-443b-...)
                            │
                 47.116.193.74:8000
                    ┌──── uvicorn ────┐
                    │  FastAPI app    │
                    │                 │
                    │  ┌─ auth  路由   │
                    │  ├─ user  路由   │
                    │  ├─ chat  路由   │── LLM (OpenClaw/DeepSeek)
                    │  ├─ voice 路由   │── 讯飞 ISE
                    │  └─ static 路由  │── 文件上传
                    │                 │
                    │  MariaDB (3306) │
                    └─────────────────┘
```

### 图表生成流程

```
用户消息
    │
    └── LLM (chat.py)
            │
            ├── 识别图表意图
            │       └── diagram_prompt.py 生成结构化提示词
            │
            └── 输出标记格式
                    ├── [SVG:...] → svg_render.py → .svg 文件 → markdown 内嵌
                    └── [IMAGE:prompt] → image_gen.py → PNG
                            │
                            └── 图片持久化到 DB / static/
                                    │
                                    └── 返回图片 URL 给前端
```

### 语音聊天流程

```
小程序录音
    │
    └── WebSocket /api/v1/voice/chat
            │
            ├── 接收音频帧 → 讯飞语音识别 (ASR)
            ├── 识别文本 → LLM 生成回复
            └── LLM 回复 → 讯飞语音合成 (TTS) → 音频帧返回
```

## 服务器

| 项目 | 值 |
|------|-----|
| IP | 47.116.193.74 |
| 提供商 | 阿里云 ECS (Alinux 4) |
| 用户 | root |
| Python | 3.11.6 |
| 数据库 | MariaDB 10.x |

## 目录结构

```
/opt/wx-miniapp-ai/
├── server/                     # 后端 FastAPI 应用
│   ├── app/
│   │   ├── main.py             # 应用入口
│   │   ├── config.py           # 配置（读取 .env）
│   │   ├── database.py         # 数据库连接池
│   │   ├── routers/
│   │   │   ├── auth.py         # 登录/登出
│   │   │   ├── user.py         # 用户资料
│   │   │   ├── chat.py         # 聊天/文件上传
│   │   │   └── voice.py        # 语音评测
│   │   ├── models/
│   │   │   ├── user.py         # wx_users CRUD
│   │   │   ├── conversation.py # 对话 CRUD
│   │   │   ├── message.py      # 消息 CRUD
│   │   │   └── session.py      # 登录 session
│   │   └── utils/
│   │       ├── auth.py         # Token 鉴权中间件
│   │       ├── llm_client.py   # LLM 调用（OpenClaw/DeepSeek）
│   │       ├── memory_manager.py # 用户记忆管理
│   │       ├── wx_api.py       # 微信 code2session
│   │       ├── xf_ise.py       # 讯飞 ISE WebSocket 客户端
│   │       ├── svg_render.py   # SVG 纯文件保存
│   │       ├── image_gen.py    # 图片生成（文生图）
│   │       ├── diagram_prompt.py # 图表 LLM 提示词
│   │       └── qwen_omni.py    # 通义千问 Omni 多模态
│   ├── .env                    # 环境变量（密钥）
│   ├── requirements.txt        # Python 依赖
│   └── logs/uvicorn.log        # 运行日志
├── uploads/                    # 用户上传文件
├── database/schema.sql         # 数据库建表
├── voice-dev-log.md            # 语音评测开发日志
├── DEVELOP.md                  # 本文件
└── API.md                      # API 文档
```

## 后端 API

所有 API 前缀 `/api/v1`，基础域名 `https://luois-james.xyz`。

### 认证模块 `/api/v1/auth`
| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| POST | /login | 微信 code 登录，返回 token | 否 |
| POST | /logout | 退出登录 | Header |

### 用户模块 `/api/v1/user`
| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| GET | /info | 获取用户资料 | Bearer |
| PUT | /profile | 更新昵称/头像 | Bearer |

### 聊天模块 `/api/v1/chat`
| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| POST | /send | 发送消息（流式 SSE 响应） | Bearer |
| GET | /conversations | 对话列表 | Bearer |
| GET | /conversations/{id}/messages | 历史消息（分页） | Bearer |
| PUT | /conversations/{id} | 重命名对话 | Bearer |
| DELETE | /conversations/{id} | 删除对话 | Bearer |
| POST | /upload | 上传文件（multipart） | Bearer |
| GET | /static/{filename} | 访问上传的文件 | 否 |
| GET | /stats | 对话统计（消息数/Token） | Bearer |
| GET | /memories | 用户记忆列表 | Bearer |

**聊天请求体**：
```json
{
  "conversation_id": null,
  "message": "Hello, how are you?"
}
```

**聊天响应**（SSE 流式）：逐 chunk 返回累积文本。

**文件上传**（multipart/form-data，字段名 `file`）：
```json
{ "url": "https://luois-james.xyz/static/abc123.txt" }
```

### 语音评测模块 `/api/v1/voice`
| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| GET | /text | 生成评测文本 | Bearer |
| POST | /assess | 提交音频评测 | Bearer |

### 语音聊天 `/api/v1/voice`
| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| WS | /chat | 实时语音对话（WebSocket） | Bearer |
| GET | /history | 语音评测历史记录 | Bearer |

**评测请求体**：
```json
{
  "audio": "<base64 WAV/PCM>",
  "text": "Hello world"
}
```

**评测响应**：
```json
{
  "score": 87,
  "comment": "表现不错，可以注意个别单词的发音和连读。",
  "dimensions": [
    {"name": "准确度", "score": 89},
    {"name": "流利度", "score": 86},
    {"name": "完整度", "score": 100},
    {"name": "标准度", "score": 75}
  ],
  "words": [
    {"content": "hello", "score": 90, "status": "good"}
  ]
}
```

## LLM 调用链

```
chat.py / voice.py
    │
    └── llm_client.chat(messages, uid=uid, model=...)
            │
            ├── 记忆注入: memory_manager.build_context(uid)
            │        └── 用户档案摘要 + 高重要度事实 (总预算 <=800字符)
            │
            ├── 优先: OpenClaw Gateway (127.0.0.1:12178/v1)
            │        └── 失败 -> fallback
            │
            └── 备用: DeepSeek API (api.deepseek.com/v1)
```

- `OPENCLAW_TOKEN` 环境变量存在时走 OpenClaw，否则直连 DeepSeek
- `chat()` 接收 `uid` 参数，自动注入记忆上下文
- `gen_title()` 生成 5-10 字对话标题

## 记忆管理

文件：`server/app/utils/memory_manager.py`

数据表 `user_memories`：
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT | 主键 |
| user_id | INT | 外键 -> wx_users |
| key | VARCHAR | 特殊标记，`_summary` 为摘要 |
| content | TEXT | 记忆内容 |
| importance | INT | 重要度 (1-10) |
| created_at | DATETIME | 创建时间 |

处理流程：
1. `build_context(uid)` — 构建对话上下文：摘要(<=300字) + 高重要度事实(<=500字)
2. `maybe_compress(uid)` — 活跃记忆 >12 条时，调用 LLM 压缩旧记忆为摘要
3. `add()` / `update_importance()` / `delete()` — 记忆增删改

## 文件上传解析

聊天 `/send` 接口在接收到消息后，调用 `_resolve_file_message()` 检查是否为本站文件 URL：

1. 普通文本 -> 原样传给 LLM
2. `https://luois-james.xyz/static/xxx.txt` -> 读取文件内容，嵌入 prompt
3. 图片 URL -> 告知 AI 无法查看
4. 二进制文件 -> 告知无法读取

支持的文本格式：.txt .md .py .js .json .xml .html .css .csv .yaml .yml .toml .ini .cfg .conf .log .sh .bat .sql .java .c .cpp .h .rs .go .rb .php .ts .tsx .jsx .vue .wxml .wxss .scss .less .env .gitignore

超过 6000 字符自动截断。原始 URL 仍保存到数据库，仅 LLM 上下文用处理后的内容。

## 语音评测

详细开发日志见 `voice-dev-log.md`。核心要点：

- **协议**：讯飞 ISE 流式 WebSocket API (`wss://ise-api.xfyun.cn/v2/open-ise`)
- **三步帧序列**：SSB（参数协商）-> TTP（评测文本）-> AUW（音频分帧）-> 结束帧
- **音频规格**：16kHz、16bit、单声道、PCM raw
- **评测引擎**：`en_vip`（英语 VIP）
- **题型**：`read_sentence`
- **文本格式**：BOM 头(U+FEFF) + 纯文本，base64 编码
- **分数转换**：ISE 返回 0-5 分制，自动 x20 转百分制
- **注意事项**：
  - TTP 帧 `status` 必须为 0（=2 会导致 ISE panic）
  - AUW 必须发送结束帧 `aus=4, status=2, data=""` 否则 60114 超时
  - 不要用 `ttp_skip` 模式（反复 48195）
  - 不要给文本加 `[content]` 标记

## 数据库

MariaDB，通过 Unix socket 连接：
```bash
mysql -S /tmp/mysql.sock -u root -p
```

表结构：
- **wx_users** — 微信用户（openid、unionid、昵称、头像）
- **user_sessions** — 登录会话（token、session_key、过期时间）
- **conversations** — 对话列表（user_id、标题）
- **messages** — 消息记录（conversation_id、role、content）
- **user_memories** — 用户记忆（user_id、内容、重要度）

完整 DDL 见 `database/schema.sql`。

## 前端

代码路径：`C:\Users\EDY\Desktop\ZLWL-WX`（Windows）
git 仓库：`https://git.weixin.qq.com/saitama/ZLWL-miniApp.git`，分支 `Test`

### 页面结构

| 页面 | 路径 | 说明 |
|------|------|------|
| 聊天 | pages/chat | 主聊天界面，侧边栏会话管理 |
| 语音 | pages/voice | 录音 + 口语评测 |
| 我的 | pages/profile | 用户资料编辑 |
| 登录 | pages/login | 微信一键登录 |

### 自定义组件

| 组件 | 说明 |
|------|------|
| chat-input | 输入框 + 发送照片/文件抽屉 |
| message-bubble | 消息气泡（文本/图片/文件卡片） |
| navigation-bar | 自定义导航栏 |
| custom-tab-bar | 自定义底部导航栏 |

### 工具模块

| 文件 | 说明 |
|------|------|
| utils/config.js | `BASE_URL` / `DEV_SKIP_LOGIN` |
| utils/request.js | 请求封装（GET/POST/PUT/DEL + 流式 SSE） |
| utils/storage.js | Token 和用户信息本地存储 |

### 配置

```javascript
// utils/config.js
BASE_URL: 'https://luois-james.xyz'  // API 基础地址
DEV_SKIP_LOGIN: true                 // 开发模式跳过登录
```

### 数据流（聊天）

```
用户输入 -> chat-input (send 事件)
  │
  ├── 文本消息 -> chat.js sendText(text)
  └── 照片/文件 -> chat.js sendMedia(type, path)
       └── uploadFile(path) -> wx.uploadFile -> /api/v1/chat/upload
       └── callChat(url) -> stream('/api/v1/chat/send', ...)
            └── 流式 SSE -> message-bubble 逐字渲染
```

## 部署

### 当前服务

```
服务        状态       端口    自启
────────────────────────────────────
uvicorn     active     8000   手动启动
cloudflared active     -      systemd
mariadb     active     3306   systemd
```

### 启动命令

```bash
# uvicorn
cd /opt/wx-miniapp-ai/server
nohup python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > logs/uvicorn.log 2>&1 &

# Cloudflare Tunnel（systemd，自动启动）
systemctl start cloudflared
systemctl enable cloudflared

# 健康检查
curl http://127.0.0.1:8000/health
curl https://luois-james.xyz/health
```

### Cloudflare 配置

```yaml
# /etc/cloudflared/config.yml
tunnel: 626935f4-443b-4d6b-a47a-2f36fc484e9d
credentials-file: /root/.cloudflared/626935f4-...json

ingress:
  - hostname: luois-james.xyz
    service: http://127.0.0.1:8000
  - service: http_status:404
```

Cloudflare DNS：CNAME `@` -> `626935f4-...cfargotunnel.com`（橙色云朵代理）
SSL/TLS 模式：Full

## 关键设计决策

1. **Cloudflare Tunnel 而非 Nginx 反代**：阿里云 ECS 需要 ICP 备案，Tunnel 绕过备案检查
2. **OpenClaw 优先 + DeepSeek 备份**：利用本地智能体能力，网络异常时自动降级
3. **文件 URL 自动解析**：LLM 无法访问外部链接，后端检测文件 URL 后主动读取内容嵌入 prompt
4. **逐词评分按分数着色**：ISE dp_message 固定为 0，改为 >=80绿/60-79黄/<60红 三档
5. **记忆压缩**：超过 12 条活跃记忆时 LLM 自动压缩为摘要，控制在 800 字符预算内
6. **ISE 协议不使用 ttp_skip**：该模式反复触发 48195，手动 TTP 帧可靠
7. **LLM 驱动的图表生成**：聊天中 LLM 输出 SVG/IMAGE 标记，服务端解析后 SVG 嵌入 markdown 由 towxml 渲染，创意图片以独立气泡返回
8. **SVG 纯文件保存**：svg_render.py 直接保存原始 SVG 文件，通过 towxml <image> 组件内嵌渲染，零失真无服务端开销
9. **图片持久化到数据库**：创意图片存入 DB + static/ 目录；SVG 示意图仅嵌入 markdown 文本，不重复存 DB
10. **qwen-image-max 图片生成**：image_gen.py 选用 Qwen Image Max 模型，中文渲染效果好
11. **服务器字体**：已安装 Noto Sans CJK 等中文字体（SVG 由客户端渲染，字体不再关键）

## 维护命令

```bash
# 查看服务状态
systemctl status cloudflared
ps aux | grep uvicorn

# 查看日志
tail -f /opt/wx-miniapp-ai/server/logs/uvicorn.log
journalctl -u cloudflared -f

# 重启服务
kill -HUP $(pgrep -f "uvicorn app.main")
pkill -f "uvicorn app.main" && cd /opt/wx-miniapp-ai/server && nohup python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > logs/uvicorn.log 2>&1 &
systemctl restart cloudflared

# 清理 Python 缓存
find /opt/wx-miniapp-ai -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find /opt/wx-miniapp-ai -type f -name "*.pyc" -delete 2>/dev/null

# Git 操作
cd /opt/wx-miniapp-ai
git pull origin master
git add -A && git commit -m "msg" && git push origin master

# 数据库
mysql -S /tmp/mysql.sock -u root -p
```
