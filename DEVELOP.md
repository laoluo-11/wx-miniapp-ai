# 微信小程序 AI 智能体 — 服务端开发文档

> 本文档面向开发者，覆盖项目结构、技术栈、数据库设计、API 接口、部署步骤、配置项说明及常见问题。

---

## 目录

0. [系统架构图与时序图](#0-系统架构图)
1. [项目结构](#1-项目结构)
2. [技术栈](#2-技术栈)
3. [数据库设计](#3-数据库设计)
4. [API 接口文档](#4-api-接口文档)
5. [部署步骤](#5-部署步骤)
6. [配置项说明](#6-配置项说明)
7. [常见问题](#7-常见问题)

---
## 0. 系统架构图与时序图

### 0.1 整体数据流架构

```
+---------------------------+
|      微信小程序            |
|   wx.login()  wx.request() |
+------------+--------------+
             |
          HTTPS (Cloudflare 代理)
             |
+------------v--------------+
|      Cloudflare            |
|   DNS + SSL终结 + CDN      |
+------------+--------------+
             |
        HTTP/HTTPS
             |
+------------v--------------+
|      Nginx (:80/:443)      |
|   HTTP->HTTPS 重定向        |
|   反向代理 -> :8080         |
+------------+--------------+
             |
             v
+------------+--------------+     +------------------+
|   FastAPI (:8080)          |<--->|   MySQL (:3306)   |
|                            |     |   wx_miniapp      |
|  /api/v1/auth/*  认证      |     |   - wx_users      |
|  /api/v1/chat/*  对话      |     |   - conversations |
|  /api/v1/user/*  用户      |     |   - messages      |
+------------+--------------+     |   - user_sessions |
             |                     +------------------+
             |
        HTTPS (API 调用)
             |
+------------v--------------+
|     DeepSeek API           |
|   deepseek-chat 模型       |
+----------------------------+
```

### 0.2 微信登录时序图

```
小程序                FastAPI            微信API            MySQL
  |                     |                   |                 |
  |-- wx.login() ------>|                   |                 |
  |<---- code ----------|                   |                 |
  |                     |                   |                 |
  |-- POST /auth/login ->|                   |                 |
  |   {code}            |                   |                 |
  |                     |-- code2session -->|                 |
  |                     |   {appid,secret,  |                 |
  |                     |    code}          |                 |
  |                     |<-- openid, --------|                 |
  |                     |    session_key    |                 |
  |                     |                   |                 |
  |                     |-- find_or_create_user ----------->|
  |                     |<-------- user_id -----------------|
  |                     |                   |                 |
  |                     |-- create_session(token) --------->|
  |                     |<-------- OK ----------------------|
  |                     |                   |                 |
  |<-- {token,user_id}--|                   |                 |
  |    is_new           |                   |                 |
```

### 0.3 对话消息时序图

```
小程序              FastAPI             MySQL           DeepSeek
  |                   |                   |                |
  |-- POST /chat/send->|                   |                |
  |   {message,        |                   |                |
  |   conversation_id} |                   |                |
  |   Auth: Bearer <t> |                   |                |
  |                   |                   |                |
  |                   |-- validate_token ------------->|   |
  |                   |<-------- user -----------------|   |
  |                   |                   |                |
  |                   |-- 新对话? create_conversation ->|   |
  |                   |<-------- cid ------------------|   |
  |                   |                   |                |
  |                   |-- save user msg --------------->|   |
  |                   |<-------- OK -------------------|   |
  |                   |                   |                |
  |                   |-- get_recent_pairs(cid,10) ---->|   |
  |                   |<-------- history ---------------|   |
  |                   |                   |                |
  |                   |-- chat(history) ------------------->|
  |                   |                   |                |
  |                   |<-- AI reply -----------------------|
  |                   |                   |                |
  |                   |-- save assistant msg----------->|   |
  |                   |<-------- OK -------------------|   |
  |                   |                   |                |
  |                   |-- 新对话? gen_title -------------->|
  |                   |<-- 标题 --------------------------|
  |                   |                   |                |
  |<-- {reply,         |                   |                |
  |    conversation_id,|                   |                |
  |    title}          |                   |                |
```

### 0.4 前端调用示意

```
小程序页面生命周期:

App Launch
  |
  v
wx.login() 获取 code
  |
  v
POST /api/v1/auth/login  {code}
  |
  v
拿到 token，存入 storage
  |
  v
进入聊天页
  |
  v
用户输入消息
  |
  v
POST /api/v1/chat/send  {message, conversation_id}
  Authorization: Bearer <token>
  |
  +-- 显示 AI 回复
  |
  +-- 新对话: 更新对话列表标题 (title)
  |
  +-- 继续对话: conversation_id 不变
```

---

## 1. 项目结构

```
wx-miniapp-ai/
├── API.md                        # API 接口文档（面向前端）
├── DEVELOP.md                    # 开发文档（本文件）
├── server/                       # 服务端
│   ├── .env                      # 环境变量（敏感信息，不提交 Git）
│   ├── requirements.txt          # Python 依赖清单
│   ├── test_llm.py               # LLM 连通性测试脚本
│   └── app/
│       ├── __init__.py
│       ├── main.py               # FastAPI 应用入口，路由注册，异常处理
│       ├── config.py             # 从 .env 加载配置项
│       ├── database.py           # MySQL 连接管理（连接池、事务）
│       ├── models/               # 数据访问层（DAO）
│       │   ├── __init__.py
│       │   ├── user.py           # 用户 CRUD
│       │   ├── session.py        # Token 会话管理
│       │   ├── conversation.py   # 对话 CRUD
│       │   └── message.py        # 消息存取
│       ├── routers/              # 路由层（API 端点）
│       │   ├── __init__.py
│       │   ├── auth.py           # /api/v1/auth/*  登录/登出
│       │   ├── user.py           # /api/v1/user/*  用户信息/更新
│       │   └── chat.py           # /api/v1/chat/*  对话/消息
│       └── utils/                # 工具层
│           ├── __init__.py
│           ├── auth.py           # Bearer Token 鉴权依赖 (Depends)
│           ├── wx_api.py         # 微信 code2session 接口封装
│           └── llm_client.py     # DeepSeek API 调用封装
└── database/
    ├── schema.sql                # 建表 DDL
    └── backup.sh                 # 数据库备份脚本
```

**分层架构说明**：

| 层级 | 目录 | 职责 |
|------|------|------|
| 路由层 | `routers/` | 定义 API 端点，参数校验，调用模型层 |
| 工具层 | `utils/` | 鉴权依赖注入、微信 API、LLM API |
| 模型层 | `models/` | 数据库 CRUD，纯函数，无路由依赖 |
| 入口层 | `main.py` | FastAPI 实例化，中间件，异常处理，启动 |

---

## 2. 技术栈

| 类别 | 技术 | 版本 | 说明 |
|------|------|------|------|
| 语言 | Python | 3.11 | conda 环境 |
| Web 框架 | FastAPI | 0.115.6 | 异步 HTTP 服务 |
| ASGI 服务器 | Uvicorn | 0.34.0 | 运行 FastAPI 应用 |
| 数据库驱动 | PyMySQL | 1.1.1 | 纯 Python MySQL 客户端 |
| HTTP 客户端 | httpx | 0.28.1 | 异步 HTTP（调微信/LLM） |
| 数据库 | MySQL | 5.7 | conda 安装，socket: `/tmp/mysql.sock` |
| LLM | DeepSeek | deepseek-chat | OpenAI 兼容接口 |
| 微信登录 | code2session | - | `api.weixin.qq.com/sns/jscode2session` |
| 反向代理 | Nginx | - | 80/443 → 8080 |
| SSL | Cloudflare | - | 代理模式，源站关闭 HTTPS |

---

## 3. 数据库设计

### 3.1 数据库信息

| 项目 | 值 |
|------|-----|
| 数据库名 | `wx_miniapp` |
| 字符集 | `utf8mb4` / `utf8mb4_unicode_ci` |
| 引擎 | InnoDB |
| 用户 | `miniapp` / `MiniApp@2024!` |
| Socket | `/tmp/mysql.sock` |

### 3.2 完整 DDL

```sql
-- 创建数据库
CREATE DATABASE IF NOT EXISTS wx_miniapp
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE wx_miniapp;

-- ============================================================
-- 表 1: wx_users — 微信用户
-- ============================================================
CREATE TABLE IF NOT EXISTS wx_users (
    id          INT AUTO_INCREMENT PRIMARY KEY  COMMENT '用户ID',
    openid      VARCHAR(64)  NOT NULL UNIQUE    COMMENT '微信OpenID，唯一标识',
    unionid     VARCHAR(64)  DEFAULT NULL       COMMENT '微信UnionID，开放平台统一ID',
    nickname    VARCHAR(100) DEFAULT NULL       COMMENT '用户昵称',
    avatar_url  VARCHAR(500) DEFAULT NULL       COMMENT '头像URL',
    phone       VARCHAR(20)  DEFAULT NULL       COMMENT '手机号',
    gender      TINYINT      DEFAULT 0         COMMENT '性别: 0=未知,1=男,2=女',
    country     VARCHAR(50)  DEFAULT NULL       COMMENT '国家',
    province    VARCHAR(50)  DEFAULT NULL       COMMENT '省份',
    city        VARCHAR(50)  DEFAULT NULL       COMMENT '城市',
    created_at  DATETIME     DEFAULT CURRENT_TIMESTAMP           COMMENT '注册时间',
    updated_at  DATETIME     DEFAULT CURRENT_TIMESTAMP
                             ON UPDATE CURRENT_TIMESTAMP         COMMENT '更新时间',
    INDEX idx_openid (openid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='微信用户表';

-- ============================================================
-- 表 2: user_sessions — 登录会话
-- ============================================================
CREATE TABLE IF NOT EXISTS user_sessions (
    id          INT AUTO_INCREMENT PRIMARY KEY  COMMENT '会话ID',
    user_id     INT           NOT NULL          COMMENT '关联用户ID',
    token       VARCHAR(128)  NOT NULL UNIQUE   COMMENT '登录Token（Bearer）',
    session_key VARCHAR(64)   NOT NULL          COMMENT '微信session_key',
    expires_at  DATETIME      NOT NULL          COMMENT '过期时间（72小时）',
    created_at  DATETIME      DEFAULT CURRENT_TIMESTAMP  COMMENT '创建时间',
    INDEX idx_token (token),
    FOREIGN KEY (user_id) REFERENCES wx_users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='登录会话表';

-- ============================================================
-- 表 3: conversations — 对话会话
-- ============================================================
CREATE TABLE IF NOT EXISTS conversations (
    id          INT AUTO_INCREMENT PRIMARY KEY  COMMENT '对话ID',
    user_id     INT           NOT NULL          COMMENT '所属用户ID',
    title       VARCHAR(100)  DEFAULT '新的对话' COMMENT '对话标题（AI自动生成）',
    created_at  DATETIME      DEFAULT CURRENT_TIMESTAMP  COMMENT '创建时间',
    updated_at  DATETIME      DEFAULT CURRENT_TIMESTAMP  COMMENT '最后更新时间',
    INDEX idx_user (user_id),
    FOREIGN KEY (user_id) REFERENCES wx_users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='对话表';

-- ============================================================
-- 表 4: messages — 消息记录
-- ============================================================
CREATE TABLE IF NOT EXISTS messages (
    id              INT AUTO_INCREMENT PRIMARY KEY  COMMENT '消息ID',
    conversation_id INT           NOT NULL          COMMENT '所属对话ID',
    role            ENUM('user','assistant','system') NOT NULL
                                                     COMMENT '角色: user=用户, assistant=AI, system=系统',
    content         TEXT          NOT NULL          COMMENT '消息内容',
    created_at      DATETIME      DEFAULT CURRENT_TIMESTAMP  COMMENT '发送时间',
    INDEX idx_conv (conversation_id),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='消息记录表';
```

### 3.3 表关系图

```
wx_users (1) ──< user_sessions (N)     # 一个用户可有多个登录会话
wx_users (1) ──< conversations (N)     # 一个用户可有多个对话
conversations (1) ──< messages (N)     # 一个对话包含多条消息
```

### 3.4 字段说明详情

#### wx_users（微信用户表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INT PK | 自增主键，系统内唯一用户ID |
| `openid` | VARCHAR(64) UNIQUE | 微信小程序用户唯一标识，每个小程序不同 |
| `unionid` | VARCHAR(64) | 微信开放平台统一ID，同一主体下多个应用共享（可选） |
| `nickname` | VARCHAR(100) | 用户昵称，为空即视为新用户（`is_new=true`） |
| `avatar_url` | VARCHAR(500) | 头像图片URL，最长500字符 |
| `phone` | VARCHAR(20) | 手机号（预留字段，当前未使用） |
| `gender` | TINYINT | 0=未知, 1=男, 2=女 |
| `country/province/city` | VARCHAR(50) | 地区信息（预留字段） |
| `created_at` | DATETIME | 注册时间，默认当前时间 |
| `updated_at` | DATETIME | 自动更新为最后修改时间 |

#### user_sessions（登录会话表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INT PK | 自增主键 |
| `user_id` | INT FK | 关联 `wx_users.id`，级联删除 |
| `token` | VARCHAR(128) UNIQUE | 64位十六进制随机字符串（`secrets.token_hex(32)`） |
| `session_key` | VARCHAR(64) | 微信返回的 session_key，用于数据解密 |
| `expires_at` | DATETIME | 过期时间，登录后 72 小时 |
| `created_at` | DATETIME | 创建时间 |

#### conversations（对话表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INT PK | 自增主键，对话ID |
| `user_id` | INT FK | 所属用户，级联删除 |
| `title` | VARCHAR(100) | 对话标题，新建默认"新的对话"，首次消息后由AI生成（5-10字） |
| `created_at` | DATETIME | 创建时间 |
| `updated_at` | DATETIME | 最后更新时间（新消息时更新），列表按此字段倒序 |

#### messages（消息记录表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INT PK | 自增主键 |
| `conversation_id` | INT FK | 所属对话，级联删除 |
| `role` | ENUM | `user`=用户发送, `assistant`=AI回复, `system`=系统（预留） |
| `content` | TEXT | 消息全文，无长度限制 |
| `created_at` | DATETIME | 消息发送时间 |

---

## 4. API 接口文档

**Base URL**: `https://luois-james.xyz`

### 4.1 鉴权说明

所有需要登录的接口，必须在请求头中携带 Token：

```
Authorization: Bearer <token>
```

Token 通过 `POST /api/v1/auth/login` 获取，有效期 **72 小时**。

### 4.2 通用错误格式

```json
{
  "message": "错误描述信息"
}
```

### 4.3 HTTP 状态码约定

| 状态码 | 含义 | 触发场景 |
|--------|------|----------|
| `200` | 成功 | 请求正常处理 |
| `400` | 请求参数错误 | code 无效、缺少必填字段、无更新字段 |
| `401` | 未授权 | Token 缺失、格式错误、过期或无效 |
| `404` | 资源不存在 | 对话不属于当前用户或已被删除 |
| `500` | 服务器内部错误 | LLM API 调用失败、数据库异常 |

---

### 接口 1：微信登录

```http
POST /api/v1/auth/login
```

**功能**：使用微信小程序 `wx.login()` 返回的临时 code 换取登录凭证。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `code` | string | 是 | `wx.login()` 返回的临时凭证，有效期约5分钟 |

**请求示例**：

```json
{
  "code": "0b1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}
```

**成功响应 (200)**：

```json
{
  "token": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
  "user_id": 1,
  "openid": "oXXXXXXXXXXXXXXXXXXXXXXXXXXX",
  "is_new": true
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `token` | string | 64位十六进制登录凭证，后续请求需携带 |
| `user_id` | int | 系统内用户ID |
| `openid` | string | 微信 OpenID |
| `is_new` | bool | `true`=新用户（无昵称），前端引导填写资料 |

**错误示例 (400)**：

```json
{
  "message": "微信API错误: invalid code (code=40029)"
}
```

**内部流程**：
1. 调用微信 `code2session` 接口换取 `openid` + `session_key`
2. 在 `wx_users` 表中查找或创建用户（`find_or_create`）
3. 判断 `nickname` 是否为空 → `is_new`
4. 创建 `user_sessions` 记录，生成 64 位随机 Token，有效期 72 小时
5. 返回 Token + 用户信息

---

### 接口 2：发送消息（核心接口）

```http
POST /api/v1/chat/send
Authorization: Bearer <token>
```

**功能**：发送消息给 AI，获取回复。不传 `conversation_id` 则新建对话。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `message` | string | 是 | 用户输入的文本消息 |
| `conversation_id` | int | 否 | 对话ID，不传或传 `null` 则新建对话 |

**请求示例（新建对话）**：

```json
{
  "message": "你好，请介绍一下自己",
  "conversation_id": null
}
```

**请求示例（继续对话）**：

```json
{
  "message": "你能帮我做什么？",
  "conversation_id": 1
}
```

**成功响应 (200) — 新建对话**：

```json
{
  "conversation_id": 1,
  "reply": "你好！我是你的AI智能助手，可以帮你解答问题、聊天、创作、学习等各种任务。有什么我可以帮你的吗？",
  "title": "自我介绍"
}
```

**成功响应 (200) — 继续对话**：

```json
{
  "conversation_id": 1,
  "reply": "我可以帮你做很多事情：回答问题、创作文案、翻译、编程辅导、学习陪伴……",
  "title": null
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `conversation_id` | int | 对话ID，前端需保存用于后续消息 |
| `reply` | string | AI 回复的完整文本 |
| `title` | string\|null | 仅新建对话时返回，AI 自动生成的对话标题（5-10字） |

**错误示例 (404)**：

```json
{
  "message": "对话不存在"
}
```

**错误示例 (500)**：

```json
{
  "message": "AI服务异常: Connection timeout"
}
```

**内部流程**：
1. 鉴权 → 获取当前用户
2. 若 `conversation_id` 为空 → 创建新对话 `conversations` 记录
3. 若 `conversation_id` 非空 → 校验对话归属
4. 保存用户消息到 `messages`（role=user）
5. 从 `messages` 获取最近 10 轮（20条）历史记录
6. 拼装 `system prompt` + 历史 → 调用 DeepSeek API
7. 保存 AI 回复到 `messages`（role=assistant）
8. 更新对话 `updated_at`
9. 若是新对话 → 调用 LLM 生成标题（5-10字），更新 `conversations.title`
10. 返回结果

---

### 接口 3：对话列表

```http
GET /api/v1/chat/conversations
Authorization: Bearer <token>
```

**功能**：获取当前用户的所有对话，按更新时间倒序排列。

**无请求参数。**

**成功响应 (200)**：

```json
[
  {
    "id": 3,
    "user_id": 1,
    "title": "Python学习路线",
    "msg_count": 8,
    "created_at": "2026-07-16 14:30:00",
    "updated_at": "2026-07-16 15:00:00"
  },
  {
    "id": 1,
    "user_id": 1,
    "title": "自我介绍",
    "msg_count": 4,
    "created_at": "2026-07-16 10:00:00",
    "updated_at": "2026-07-16 10:05:00"
  }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | int | 对话ID |
| `user_id` | int | 所属用户ID |
| `title` | string | 对话标题 |
| `msg_count` | int | 该对话的消息总数（user + assistant） |
| `created_at` | string | 创建时间 |
| `updated_at` | string | 最后更新时间，列表以此字段倒序 |

> 返回最近 50 条对话，按 `updated_at DESC` 排序。

---

### 接口 4：加载对话历史

```http
GET /api/v1/chat/conversations/{id}/messages
Authorization: Bearer <token>
```

**功能**：加载指定对话的完整消息历史，用于进入对话时恢复上下文。

**路径参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | int | 对话ID |

**成功响应 (200)**：

```json
{
  "conversation": {
    "id": 1,
    "title": "自我介绍",
    "created_at": "2026-07-16 10:00:00",
    "updated_at": "2026-07-16 10:05:00"
  },
  "messages": [
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！我是你的AI助手，有什么可以帮你的？"},
    {"role": "user", "content": "你能帮我做什么"},
    {"role": "assistant", "content": "我可以帮你解答问题、创作、编程……"}
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `conversation` | object | 对话基本信息 |
| `messages` | array | 消息列表，按发送时间正序（最早在前） |
| `messages[].role` | string | `user`=用户, `assistant`=AI 回复 |
| `messages[].content` | string | 消息内容 |

> 最多返回 40 条消息。

**错误示例 (404)**：

```json
{
  "message": "对话不存在"
}
```

---

### 接口 5：删除对话

```http
DELETE /api/v1/chat/conversations/{id}
Authorization: Bearer <token>
```

**功能**：删除指定对话及其所有消息（级联删除）。

**路径参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `id` | int | 对话ID |

**成功响应 (200)**：

```json
{
  "msg": "ok"
}
```

**错误示例 (404)**：

```json
{
  "message": "对话不存在"
}
```

> 删除操作会级联删除 `messages` 表中所有关联消息（外键 `ON DELETE CASCADE`）。

---

### 接口 6：退出登录

```http
POST /api/v1/auth/logout
Authorization: Bearer <token>
```

**功能**：使当前 Token 失效，删除服务端会话记录。

**无请求体。**

**成功响应 (200)**：

```json
{
  "msg": "ok"
}
```

> Token 被从 `user_sessions` 表中删除后立即失效，即使未到 72 小时过期时间。

**内部流程**：
1. 从 `Authorization` 头提取 Token
2. 删除 `user_sessions` 中对应记录

---

### 接口 7：获取用户信息

```http
GET /api/v1/user/info
Authorization: Bearer <token>
```

**功能**：获取当前登录用户的详细信息。

**无请求参数。**

**成功响应 (200)**：

```json
{
  "id": 1,
  "openid": "oXXXXXXXXXXXXXXXXXXXXXXXXXXX",
  "nickname": "张三",
  "avatar_url": "https://thirdwx.qlogo.cn/xxxxxx",
  "phone": null,
  "created_at": "2026-07-16 09:00:00"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | int | 用户ID |
| `openid` | string | 微信 OpenID |
| `nickname` | string\|null | 用户昵称，空表示未设置 |
| `avatar_url` | string\|null | 头像URL |
| `phone` | string\|null | 手机号（预留） |
| `created_at` | string | 注册时间 |

---

### 接口 8：更新用户资料

```http
PUT /api/v1/user/profile
Authorization: Bearer <token>
```

**功能**：更新当前用户的昵称和/或头像。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `nickname` | string | 否 | 新昵称 |
| `avatar_url` | string | 否 | 新头像URL |

**请求示例**：

```json
{
  "nickname": "新昵称",
  "avatar_url": "https://example.com/avatar.jpg"
}
```

**成功响应 (200)**：

```json
{
  "msg": "ok"
}
```

**错误示例 (400)**：

```json
{
  "message": "无更新字段"
}
```

> 仅传需要更新的字段即可，未传的字段保持不变。两个字段都可不传，但至少传一个。

---

### 4.4 附：健康检查

```http
GET /health
```

```json
{
  "status": "ok"
}
```

```http
GET /
```

```json
{
  "service": "AI Chat Server",
  "version": "1.0"
}
```

---

## 5. 部署步骤

### 5.1 环境要求

| 组件 | 版本/要求 |
|------|-----------|
| 操作系统 | Linux (Ubuntu 20.04+) |
| Python | 3.11+ (conda) |
| MySQL | 5.7 (conda, socket `/tmp/mysql.sock`) |
| Nginx | 1.18+ |

### 5.2 完整部署流程

#### 第一步：部署 MySQL 并初始化数据库

```bash
# 初始化数据库（使用 schema.sql）
mysql -S /tmp/mysql.sock -u root -p < /home/dfzz/wx-miniapp-ai/database/schema.sql

# 创建应用用户并授权
mysql -S /tmp/mysql.sock -u root -p -e "
CREATE USER IF NOT EXISTS 'miniapp'@'localhost' IDENTIFIED BY 'MiniApp@2024!';
GRANT ALL PRIVILEGES ON wx_miniapp.* TO 'miniapp'@'localhost';
FLUSH PRIVILEGES;
"

# 验证
mysql -S /tmp/mysql.sock -u miniapp -pMiniApp@2024! -e "USE wx_miniapp; SHOW TABLES;"
```

#### 第二步：安装 Python 依赖

```bash
cd /home/dfzz/wx-miniapp-ai/server
pip install -r requirements.txt
```

#### 第三步：配置环境变量

```bash
cp /home/dfzz/wx-miniapp-ai/server/.env.example /home/dfzz/wx-miniapp-ai/server/.env
vim /home/dfzz/wx-miniapp-ai/server/.env
```

必填配置项（详见第 6 节）：

```
WX_APPID=wx你的小程序AppID
WX_SECRET=你的小程序Secret
DB_PASSWORD=MiniApp@2024!
LLM_API_KEY=sk-your-deepseek-api-key
```

#### 第四步：测试 LLM 连通性

```bash
cd /home/dfzz/wx-miniapp-ai/server
python test_llm.py
# 预期输出: API_OK: OK
```

#### 第五步：启动服务

**方式 A：手动 nohup 启动（开发/测试）**

```bash
cd /home/dfzz/wx-miniapp-ai/server
nohup uvicorn app.main:app --host 127.0.0.1 --port 8080 > /home/dfzz/logs/uvicorn.log 2>&1 &
```

**方式 B：systemd 服务（生产推荐）**

创建服务文件 `/etc/systemd/system/wx-miniapp-ai.service`：

```ini
[Unit]
Description=微信小程序 AI 智能体服务
After=network.target mysql.service

[Service]
Type=simple
User=dfzz
WorkingDirectory=/home/dfzz/wx-miniapp-ai/server
Environment="PATH=/home/dfzz/anaconda3/bin:/usr/bin:/bin"
ExecStart=/home/dfzz/anaconda3/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启用并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable wx-miniapp-ai
sudo systemctl start wx-miniapp-ai
sudo systemctl status wx-miniapp-ai
```

#### 第六步：配置 Nginx 反向代理

Nginx 配置文件 `/etc/nginx/sites-available/wx-miniapp-ai`：

```nginx
server {
    listen 80;
    server_name luois-james.xyz;

    # Cloudflare 代理 → 真实 IP
    set_real_ip_from 173.245.48.0/20;
    set_real_ip_from 103.21.244.0/22;
    set_real_ip_from 103.22.200.0/22;
    set_real_ip_from 103.31.4.0/22;
    set_real_ip_from 141.101.64.0/18;
    set_real_ip_from 108.162.192.0/18;
    set_real_ip_from 190.93.240.0/20;
    set_real_ip_from 188.114.96.0/20;
    set_real_ip_from 197.234.240.0/22;
    set_real_ip_from 198.41.128.0/17;
    set_real_ip_from 162.158.0.0/15;
    set_real_ip_from 104.16.0.0/13;
    set_real_ip_from 104.24.0.0/14;
    set_real_ip_from 172.64.0.0/13;
    set_real_ip_from 131.0.72.0/22;
    real_ip_header CF-Connecting-IP;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

启用站点：

```bash
sudo ln -sf /etc/nginx/sites-available/wx-miniapp-ai /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

#### 第七步：配置 Cloudflare SSL

1. 域名 DNS 指向 Cloudflare（橙色云朵，代理模式）
2. SSL/TLS 模式设为 **Full (strict)** 或 **Full**
3. 源站无需配置 HTTPS 证书（Cloudflare 边缘终止 SSL）

#### 第八步：设置数据库自动备份

```bash
# 编辑 crontab
crontab -e

# 每天凌晨 2 点备份，保留最近 7 天
0 2 * * * /home/dfzz/wx-miniapp-ai/database/backup.sh
```

### 5.3 部署验证

```bash
# 1. 检查服务是否启动
curl http://127.0.0.1:8080/health
# 预期: {"status":"ok"}

# 2. 通过域名验证
curl https://luois-james.xyz/health
# 预期: {"status":"ok"}

# 3. 测试登录（需要真实小程序 code）
curl -X POST https://luois-james.xyz/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"code": "0b1xxxxxxxxx"}'
```

---

## 6. 配置项说明

所有配置从 `/home/dfzz/wx-miniapp-ai/server/.env` 加载。

### 完整配置清单

```bash
# ========== 微信小程序配置 ==========
WX_APPID=wx1234567890abcdef          # 小程序 AppID（微信公众平台获取）
WX_SECRET=your_secret_here           # 小程序 AppSecret（微信公众平台获取）

# ========== 数据库配置 ==========
DB_HOST=localhost                    # MySQL 主机
DB_PORT=3306                         # MySQL 端口
DB_USER=miniapp                      # 数据库用户名
DB_PASSWORD=MiniApp@2024!            # 数据库密码
DB_NAME=wx_miniapp                   # 数据库名

# ========== LLM 配置 ==========
LLM_API_KEY=sk-your-deepseek-key     # DeepSeek API Key
LLM_BASE=https://api.deepseek.com/v1 # API 基础地址（支持任何 OpenAI 兼容接口）
LLM_MODEL=deepseek-chat              # 模型名称

# ========== AI 行为配置 ==========
SYSPROMPT=你是一个友好的AI助手。      # 系统提示词（对 LLM 的角色设定）
MAX_HIST=10                          # 上下文最多携带的对话轮数（每轮含一问一答两条）

# ========== 服务配置 ==========
HOST=127.0.0.1                       # 监听地址（生产环境不要改为 0.0.0.0，由 Nginx 代理）
PORT=8080                            # 监听端口
DEBUG=false                          # 调试模式（true=开启热重载）
```

### 配置项详细说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `WX_APPID` | `""` | **必填**。微信小程序 AppID，登录功能依赖此项 |
| `WX_SECRET` | `""` | **必填**。微信小程序 AppSecret，务必保密 |
| `DB_HOST` | `localhost` | MySQL 地址。conda MySQL 使用 `localhost` + socket |
| `DB_PORT` | `3306` | MySQL 端口 |
| `DB_USER` | `miniapp` | 数据库用户 |
| `DB_PASSWORD` | `""` | 数据库密码 |
| `DB_NAME` | `wx_miniapp` | 数据库名 |
| `LLM_API_KEY` | `""` | **必填**。DeepSeek API Key，在 [platform.deepseek.com](https://platform.deepseek.com) 获取 |
| `LLM_BASE` | `https://api.deepseek.com/v1` | API Base URL。如需切换其他模型（如 OpenAI、通义千问），修改此项 |
| `LLM_MODEL` | `deepseek-chat` | 模型名。DeepSeek 支持 `deepseek-chat` 和 `deepseek-reasoner` |
| `SYSPROMPT` | `你是一个友好的AI助手。` | 系统提示词，定义 AI 角色和行为风格 |
| `MAX_HIST` | `10` | 上下文历史轮数。值越大 Token 消耗越多；设为 0 则不带历史 |
| `HOST` | `127.0.0.1` | 监听地址。生产环境保持 `127.0.0.1` |
| `PORT` | `8080` | 监听端口 |
| `DEBUG` | `false` | 设为 `true` 开启 Uvicorn 热重载（开发用，生产请关闭） |

---

## 7. 常见问题

### 7.1 微信登录返回 400 "invalid code"

**原因**：
1. `code` 已过期（有效期约 5 分钟，且只能使用一次）
2. `WX_APPID` 或 `WX_SECRET` 配置错误
3. 小程序未上线，但使用了正式环境的 AppID（开发阶段需在微信开发者工具中"详情→不校验合法域名"）

**解决**：
- 确认 `.env` 中 `WX_APPID` 和 `WX_SECRET` 正确
- 每次 `wx.login()` 获取新 code，不要重复使用

### 7.2 AI 回复异常 / 500 错误

**原因**：
1. DeepSeek API Key 无效或余额不足
2. 网络无法访问 `api.deepseek.com`
3. `LLM_BASE` 配置错误

**排查**：
```bash
# 运行测试脚本
cd /home/dfzz/wx-miniapp-ai/server && python test_llm.py

# 若输出 API_ERR，检查 .env 中 LLM_API_KEY 是否正确
# 若超时，检查服务器能否访问外网
curl -I https://api.deepseek.com
```

### 7.3 MySQL 连接失败

**症状**：服务启动报错 `Can't connect to MySQL server`

**排查**：
```bash
# 检查 socket 是否存在
ls -la /tmp/mysql.sock

# 测试连接
mysql -S /tmp/mysql.sock -u miniapp -pMiniApp@2024! -e "SELECT 1"

# 若失败，检查 MySQL 是否运行
ps aux | grep mysql
```

### 7.4 Token 过期 / 401 错误

**说明**：Token 有效期 72 小时。过期后前端需重新调用 `wx.login()` 获取新 Token。
系统不会自动刷新 Token，这是合理设计——微信小程序 `wx.login()` 是静默的，无需用户操作。

### 7.5 如何切换 LLM 模型？

修改 `.env` 配置：

```bash
# 例如切换到 DeepSeek Reasoner（推理模型）
LLM_MODEL=deepseek-reasoner

# 或者切换到 OpenAI
LLM_BASE=https://api.openai.com/v1
LLM_MODEL=gpt-4o
LLM_API_KEY=sk-your-openai-key
```

只要目标 API 兼容 OpenAI Chat Completions 格式即可。

### 7.6 如何自定义 AI 角色？

修改 `.env` 中的 `SYSPROMPT`：

```bash
# 例如：编程助手
SYSPROMPT=你是一个专业的编程助手，擅长 Python 和 JavaScript。回答问题时请直接给出可运行的代码，并附带简要解释。
```

修改后**无需重启服务**（每次请求都会读取配置）。

### 7.7 生产环境性能优化建议

1. **数据库连接池**：当前每次请求新建连接，高并发时建议引入连接池（如 `DBUtils` 或 SQLAlchemy）
2. **LLM 流式输出**：当前为同步等待全部回复，建议改造为 SSE（Server-Sent Events）流式输出，提升用户体验
3. **Redis 缓存**：Token 验证每次查库，高并发时可引入 Redis 缓存 Token
4. **日志**：建议集成 `logging` 模块输出结构化日志，便于排查问题
5. **限流**：建议接入 `slowapi` 对 `/api/v1/chat/send` 做频率限制

### 7.8 日志查看

```bash
# nohup 方式
tail -f /home/dfzz/logs/uvicorn.log

# systemd 方式
sudo journalctl -u wx-miniapp-ai -f

# Nginx 访问日志
tail -f /var/log/nginx/access.log

# Nginx 错误日志
tail -f /var/log/nginx/error.log
```

### 7.9 服务重启

```bash
# systemd 方式
sudo systemctl restart wx-miniapp-ai

# nohup 方式
# 查找进程并终止
ps aux | grep uvicorn | grep -v grep | awk '{print $2}' | xargs kill
# 重新启动
nohup uvicorn app.main:app --host 127.0.0.1 --port 8080 > /home/dfzz/logs/uvicorn.log 2>&1 &
```

### 7.10 微信小程序合法域名配置

在小程序管理后台 **开发 → 开发管理 → 服务器域名** 中配置：

| 类型 | 域名 |
|------|------|
| request 合法域名 | `https://luois-james.xyz` |

> 开发阶段可在微信开发者工具中勾选"不校验合法域名"，上线前必须配置。
