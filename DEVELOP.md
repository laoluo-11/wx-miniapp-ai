# ZLWL 智能聊天 — 开发文档

> 最后更新：2026-08-10

## 项目概述

ZLWL（智领未来）是一个英语口语学习微信小程序，核心功能包括 AI 智能聊天和语音评测。用户可与 AI 自由对话、上传文件让 AI 分析，还能录音进行英语口语发音评测。


## 2026-08-10 图片理解切换为 Qwen VL 直连

### 问题
OpenRouter API Key 失效导致图片理解（视觉描述）不可用。

### 解决
`_vision_call` 改用阿里云百炼 Qwen MaaS 直连（`qwen-vl-max`），本地下载图片转 base64 发送。
`chat_stream`/`chat` 中的 `OPENROUTER_KEY` 检查替换为 `QWEN_API_KEY`。

涉及文件：
- `server/app/utils/llm_client.py` — _vision_call 重写 + 条件替换

## 2026-08-10 深度搜索降级修复

### 问题
OpenRouter API Key 失效（401 "User not found"），深度搜索报错 `[Deep error: OpenRouter error 401: ...]`。

### 解决
`deep_agent.py` 重写：OpenRouter 调用失败时自动降级为普通 DeepSeek 对话（通过 `chat_stream`），不再抛异常。
深度搜索按钮仍可用，只是联网搜索暂不可用（待新 API Key）。

涉及文件：
- `server/app/utils/deep_agent.py` — try/except 包裹 OpenRouter 调用，失败降级

## 2026-08-05 TTS公式语音清洗（方案E 正则）

voice.py `/tts` 端点新增 `_clean_latex()` + `_match_brace()` — 文本送阿里NLS前用Python正则将LaTeX公式转为口语化中文。
- `\frac{a}{b}` → "b分之a"（栈匹配花括号处理嵌套）
- `x^{n}` / `x^2` → "x的n次方"/"x的2次方"
- `\sqrt[n]{x}` / `\sqrt{x}` → "x开n次方"/"根号x"
- `x_{n}` / `x_1` → "x下标n"/"x下标1"
- 希腊字母、符号命令翻译、$$/$包裹符剥离
- 连续拉丁字母间插空格防TTS连读（mc → m c）


## 2026-08-06 负号翻译

### 调整 (voice.py _clean_latex 7.6)
- `-5` → 负5；`-0.5` → 负0.5；`-x` → 负x（前面是数字/字母/右括号时判为减法，保留不动，如 x-5）
- 涉及文件：`server/app/routers/voice.py`

## 2026-08-06 括号不再播报

### 调整 (voice.py _clean_latex)
- 所有括号命令直接删除、不播报：\left( \right) \big 系列、\{ \}（集合）、\langle \rangle（内积）、\lfloor \rfloor（取整）、普通 ASCII () [] {}
- 保留语义：\left| x \right| → x的绝对值、\mid → 满足
- 普通括号删除放在 \text{} 清理之后，避免破坏 \text{...} 正则匹配
- 涉及文件：`server/app/routers/voice.py`

## 2026-08-06 语音播报生动性优化（停顿 + 语速 + prompt 引导）

### 停顿注入 (voice.py)
- `_split_sentences` 重写：max_len 200 → 80，返回 [(text, para_end)]，段落边界就地结算不混段
- 新增 `_pause_ms()`：按句末标点映射停顿 —— 段落 500ms / 。！？… 400ms / .!? 500ms / ；; 350ms / ：: 300ms / 逗号 200ms / 、 150ms / 默认 300ms（2026-08-06 段落 800→500、句号 600→400 试听微调）
- `/tts` 返回每段 `pauseMs` 字段，前端播完该段后按此停顿再播下一段

### 语速/音调 (tts_ali.py)
- `speech_rate` 0 → -10（略慢、更从容）；`pitch_rate` 0 → 5（略高、更亲切）
- TTS 缓存 key 加版本 `tts_v2|` 前缀，强制旧缓存失效，新参数生效

### AI 输出引导 (chat.py)
- `_build_system_prompt` 新增 [语音播报要求]：多用短句（≤40字）、口语化语气词、段落分明空行分隔、避免超长复合句

涉及文件：
- `server/app/routers/voice.py`
- `server/app/utils/tts_ali.py`
- `server/app/routers/chat.py`
- 前端 `message-bubble.js`/`chat.js`（见前端开发日志）

## 2026-08-06 TTS LaTeX 括号翻译

### 括号命令口语化 (voice.py _clean_latex)
- `\left(` `\right)` `\big(` 系列 → 左括号/右括号；`\left[` 系列 → 左中括号/右中括号
- `\{` `\}`（集合）→ 左花括号/右花括号；`\langle` `\rangle` → 左尖括号/右尖括号
- `\left| x \right|` 配对 → x的绝对值；`\lvert`/`\rvert`/`\vert`/`\Vert` → 竖线
- `\lfloor`/`\rfloor`/`\lceil`/`\rceil` → 取整符号；`\mid` → 满足
- 普通 ASCII `()` `[]` `{}` 也翻译为左/右括号（全角中文标点不受影响）
- `(x+1)^2` / `(x+1)^{2}` → (x+1)的2次方（括号后跟上标补充处理）
- 残留的 `\left`/`\right` 命令（后跟未覆盖符号时）自动清除
- 涉及文件：`server/app/routers/voice.py`

## 2026-08-06 SVG 图表渲染规范优化

### SVG 规范调整 (diagram_prompt.py)
- DIAGRAM_SYSTEM_PROMPT 追加约束：SVG 内部组件尽量浅色背景+黑色文字，禁止深色背景+黑色文字
- 原因：深色背景配黑色文字导致图表内容不可读
- 涉及文件：
  - 修改 `server/app/utils/diagram_prompt.py`

## 2026-08-06 TTS语音播报全面优化 + LaTeX渲染修复

### TTS 清洗管线 (`voice.py`)

`/tts` 端点新增三层清洗管线：`_clean_units()` → `_clean_markdown()` → `_clean_latex()` → 阿里NLS

#### _clean_units() — 计量单位过滤（50+单位）
- 长度：nm/mm/cm/dm/km/m、面积/体积复合单位
- 重量：t/kg/mg/g
- 温度：°C/°F/K/°(角度)
- 电学：V/A/W/Hz/Ω 及 kV/mA/kW/GHz 等
- 力/压强/能量：N/Pa/J/cal 及 kN/MPa/kJ/kcal
- 时间：ms/s/min/h、容积：mL/L
- 其他：mol/dB/mAh/kWh/Mbps

#### _clean_markdown() — Markdown格式过滤
- **粗体** *斜体* `代码` ```代码块``` ~~删除~~
- ##标题、-列表、1.有序、>引用、---水平线
- [链接](url) → 文字

#### _clean_latex() — LaTeX公式翻译
- \frac、\sqrt、幂/下标（栈匹配花括号处理嵌套）
- 希腊字母音译、符号命令（×÷±∞∑∫lim→≠≈≥≤）
- 三角函数音译：\sin→萨茵、\cos→口萨茵、\tan→探针特、\arcsin→阿克萨茵等
- 对数：\log→烙格、\ln→烙恩
- 集合：∀∃∈∪∩∅、几何：∠△∥⊥≅≡、推理：∴∵⇒⇔
- 省略号：\ldots/\cdots、向量：\vec/\overrightarrow
- 微积分：∇梯度、∂偏导、∝正比于

### LaTeX SVG 渲染修复 (`latex_server.js` + `latex_proxy.py`)
- 背景 #000 → transparent（公式透明底）
- CSS 选择器 path/text/use → *（覆盖 line/rect 分数线）
- 缓存 key 加版本号 v2 强制刷新


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

---

## 2026-07-27 更新

### 域名迁移
- 域名从 `luois-james.xyz` 迁移到 `yyzhilingweilai.com`
- 安装了 Let's Encrypt SSL 证书，Nginx 配置 HTTPS
- 后端所有硬编码 URL 全部更新，旧域名文件清理逻辑已兼容

### 管理后台
- 新增 `/admin` 管理后台页面（HTML5 SPA）
- 支持用户 CRUD、对话查看、评测/记忆/文件管理
- 管理 API 位于 `/api/v1/admin/*`，Token 有效期 8 小时
- 管理员密码在 `server/.env` 的 `ADMIN_PASSWORD` 配置

### 会话标题自动命名
- 新会话默认显示创建时间戳
- 第一条消息发送后，AI 根据对话内容自动生成标题（5-15 字）
- 使用 DeepSeek 生成标题（不依赖 OpenClaw）

### 手机号绑定
- 新增 `POST /api/v1/user/bind-phone` 解密微信手机号
- 一个手机号只能绑定一个账号

### 语音测评
- 前端新增"换一句"按钮，可重新生成评测文本

### uvicorn 并发提升
- Workers 从 2 提升到 4，并发能力翻倍

---

## 2026-07-28 更新 — 用户VIP系统 + 用量监控

### 会员系统
- `wx_users` 表新增 `role`（user/vip）和 `vip_expires_at` 字段
- 管理后台支持设置 VIP 时长（天数 / -1永久 / 0取消）
- 区分普通用户和会员的用量限额
- 会员到期自动降级（auth 中间件检查）

### 用量监控
- 新增 `usage_stats` 表按天统计用量
- 统一限额：chat:20/120, voice_assess:3/15, speak:20/120, upload:3/15
- 各端点自动埋点追踪，超限返回 429
- 前端个人中心用量进度条 + VIP 标识 + 到期时间
- 管理后台用户详情增加「用量」标签页

### 写入修复
- 修复 chat.py `/send` 用量追踪代码未插入问题
- 修复 admin.py VIP 更新代码未插入问题
- 修复 admin 页面 `id^=t` 选择器误匹配 tabBar 导致标签页消失
- 管理后台查看消息支持图片缩略图显示
- 管理后台 JS 全面改用传统 for 循环，避免兼容性问题


---

## 2026-07-28 意图分类 + 图片路由优化

### 意图分类器 (intent.py)

在聊天流程前增加独立的意图判断步骤，将用户请求分为四类：

| intent | 触发条件 | 处理方式 |
|--------|----------|----------|
| `image` | "画一匹马"等纯生图请求 | 跳过 LLM，直接千问 qwen-image-max 生图 |
| `diagram` | 流程图/架构图/几何等配图需求 | LLM 回复文字 + SVG 示意图 |
| `analyze` | 上传图片/文件要求分析 | LLM 分析文件内容 |
| `text` | 普通问答/翻译/计算 | 纯文字 LLM 回复 |

优点：
- 纯生图请求从 ~10s 降至 ~2s
- 纯文字聊天不再加载 diagram prompt，省 token
- 分类失败自动降级为 text
- 环境变量 `USE_INTENT_CLASSIFIER=true/false` 可随时回退

涉及文件：
- 新增 `server/app/utils/intent.py`
- 修改 `server/app/config.py` — 新增开关
- 修改 `server/app/routers/chat.py` — /send 和 /send-deep-stream 新增路由

### Bugfix

- AI 生成图片未写入 user_files 表 → 管理后台「用户-文件」看不到
- 管理后台删文件只删 DB 不删磁盘 (static/ 前缀文件) → 已修复 _cleanup_file


---

## 2026-07-28 审核合规 + 手机号绑定升级

### 手机号绑定升级为微信新版 API
- 旧版 AES 解密方式已弃用，改用 code 换取手机号
- 新增 `_get_access_token()` 和 `_get_phone_by_code()` 
- 向后兼容旧版 encrypted_data 方式

### AI 角色预设
- 更新 `DIAGRAM_SYSTEM_PROMPT`，添加身份设定和自我介绍规范
- 禁止 AI 提及 OpenClaw、DeepSeek 等底层技术信息

## 2026-08-04 语音播报 + ASR 语音转文字

### 语音播报 (TTS)
- 前端 AI 气泡新增 🔊 播报按钮，点击调 `/api/v1/voice/tts`（阿里云 NLS），分段播放
- 导航栏新增 🔊/🔇 全局自动播放开关，开启后 AI 回复完自动播报
- 开关状态持久化到 `wx.Storage`
- 深度模式按钮从导航栏移至输入栏发送按钮旁，避免导航栏拥挤
- 默认音色从 `xiaoyun` 换为 `ruoxi`（若溪，更自然）
- TTS 缓存自动清理：超过 200 个文件或 7 天未访问自动删除，每小时扫描一次

### 语音转文字 (ASR)
- 新增 `/api/v1/chat/asr` 端点：长按输入框录音 → 上传 → 阿里云 NLS 识别 → 自动发送
- 新增 `server/app/utils/asr_ali.py`，复用 tts_ali 的 token 管理
- 比之前用 Qwen-Omni 方案快 10 倍+

### 前端 UI 调整
- 输入栏整体放大：按钮 60→72rpx，字号 28→30rpx，内边距增大
- 键盘弹起仍正确抬升，不覆盖输入框

涉及文件：
- 新增 `server/app/utils/asr_ali.py`
- 修改 `server/app/utils/tts_ali.py` — 缓存清理 + 默认音色
- 修改 `server/app/routers/chat.py` — ASR 端点
- 修改 `server/app/routers/voice.py` — 默认音色
- 前端多项（见前端开发日志）



## 2026-08-04 LaTeX 渲染升级 + 深度搜索修复 + 华为兼容

### LaTeX 公式渲染：codecogs → 本地 MathJax 3
- 原因：codecogs 海外服务从阿里云北京经常超时，首次公式渲染慢且不稳定
- 新增 `latex_render.js`（MathJax 3 Node 脚本）+ `latex_server.js`（常驻 HTTP 服务，端口 9123）
- 重写 `latex_proxy.py`：不再转发 codecogs，改调本地 MathJax
- 效果：首次渲染从 ~400ms（spawn 子进程）降至 ~20ms（常驻服务），快了 20 倍
- 公式统一黑底白字，深色主题友好
- 启动方式：`cd /opt/wx-miniapp-ai/server && bash start_latex.sh`

### 深度搜索修复
- 问题：deep_agent.py 用 DuckDuckGo HTML 抓取做联网搜索，阿里云北京连不上
- 修复：重写 `deep_agent.py`，改用 OpenRouter `deepseek/deepseek-chat:online`
- DeepSeek 原生联网搜索，结果自动注入回复，带引用链接
- 去掉了本地 DuckDuckGo + code_exec 工具循环，代码从 213 行精简到 ~70 行

### TTS 音色 + 缓存清理
- 默认音色 `xiaoyun` → `ruoxi`（若溪），更自然
- TTS 缓存自动清理：超过 200 个文件或 7 天未访问自动删除

### 前端大改（见前端开发日志）
- tabBar 移到顶部导航栏内，底部彻底干净
- 华为真机兼容：100vh→100%、safeArea 兜底、全局键盘监听
- 语音录音路由守卫、TTS 文本清洗、图片预览等

涉及文件：
- 新增 `server/app/utils/latex_render.js`、`server/app/utils/latex_server.js`、`server/app/utils/start_latex.sh`
- 重写 `server/app/utils/deep_agent.py`
- 修改 `server/app/routers/latex_proxy.py`
- 前端多项

