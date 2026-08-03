# ZLWL 智能聊天 — API 文档

**更新日期**: 2026-07-27
**Base URL**: `https://yyzhilingweilai.com`
**API 前缀**: `/api/v1`

---

## 鉴权

除登录和静态文件外，所有接口需在 Header 携带 Token：

```
Authorization: Bearer ***
```

Token 通过 `/api/v1/auth/login` 获取。

---

## 通用约定

| 状态码 | 含义 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | Token 无效或过期 |
| 404 | 资源不存在 |
| 500 | 服务器错误 |

错误响应格式：
```json
{"message": "错误描述"}
```

---

## 1. 认证

### 微信登录
```
POST /api/v1/auth/login
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | string | 是 | `wx.login()` 返回的临时 code |

请求：
```json
{"code": "0b1xxxxx..."}
```

响应：
```json
{
    "token": "***",
    "user_id": 1,
    "openid": "oXXXX...",
    "is_new": true
}
```

| 字段 | 说明 |
|------|------|
| token | 登录凭证 |
| user_id | 用户 ID |
| openid | 微信 OpenID |
| is_new | 是否新用户（无昵称） |

### 退出登录
```
POST /api/v1/auth/logout
Authorization: Bearer ***
```

响应：
```json
{"msg": "ok"}
```

---

## 2. 用户

### 获取用户信息
```
GET /api/v1/user/info
Authorization: Bearer ***
```

响应：
```json
{
    "id": 1,
    "openid": "oXXXX...",
    "nickname": "张三",
    "avatar_url": null,
    "phone": null,
    "created_at": "2026-07-21 09:00:00"
}
```

### 更新用户资料
```
PUT /api/v1/user/profile
Authorization: Bearer ***
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| nickname | string | 否 | 昵称 |
| avatar_url | string | 否 | 头像 URL |

请求：
```json
{"nickname": "新昵称", "avatar_url": "https://..."}
```

响应：
```json
{"msg": "ok"}
```

---

## 3. 聊天

### 发送消息（流式）
```
POST /api/v1/chat/send
Authorization: Bearer ***
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| message | string | 是 | 消息文本或文件 URL |
| conversation_id | int | 否 | 不传则新建对话 |

请求：
```json
{
    "message": "你好，请介绍一下自己",
    "conversation_id": null
}
```

**流式响应**（SSE 分块传输）：

流式推送过程中，正文内容逐块返回。流结束时，会追加一行 META 标记：

```
你好！
你好！我是
你好！我是你的AI助手……
__META__{"conversation_id":1,"reply":"你好！我是你的AI助手……","title":"自我介绍","image_url":""}
```

**META 格式说明**：

| 字段 | 说明 |
|------|------|
| conversation_id | 对话 ID |
| reply | AI 回复全文 |
| title | 仅新建对话返回，AI 自动生成标题 |
| image_url | AI 生成的配图/示意图 URL（无图片时为空字符串） |

`__META__` 行以 `__META__` 前缀开头，后跟一个 JSON 对象。客户端应从流中解析该行以获取对话元信息。

### 图表/示意图生成

系统会根据对话内容自动判断是否需要生成配图：

- **SVG 图表**：当对话涉及流程、架构、数据关系等内容时，AI 自动生成 SVG 示意图
- **创意配图**：适用于故事、诗歌等创意场景，AI 生成相应的创意图片
- 生成的图片 URL 通过流末尾的 `__META__` 中的 `image_url` 字段返回

无需额外参数，系统自动完成生成。

### 对话列表
```
GET /api/v1/chat/conversations
Authorization: Bearer ***
```

响应（按更新时间倒序）：
```json
[
    {
        "id": 1,
        "user_id": 1,
        "title": "自我介绍",
        "msg_count": 4,
        "created_at": "2026-07-21 10:00:00",
        "updated_at": "2026-07-21 10:05:00"
    }
]
```

### 获取历史消息
```
GET /api/v1/chat/conversations/{id}/messages?limit=20&before=1712345678000
Authorization: Bearer ***
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| limit | int | 否 | 每页条数，默认 40，最大 100 |
| before | int | 否 | 毫秒时间戳，加载更早消息 |

响应（扁平数组）：
```json
[
    {"role": "user", "content": "你好", "time": "2026-07-21 10:00:00"},
    {"role": "assistant", "content": "你好！", "time": "2026-07-21 10:00:01"}
]
```

### 重命名对话
```
PUT /api/v1/chat/conversations/{id}
Authorization: Bearer ***
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| title | string | 是 | 新标题 |

请求：
```json
{"title": "新标题"}
```

响应：
```json
{"msg": "ok"}
```

### 删除对话
```
DELETE /api/v1/chat/conversations/{id}
Authorization: Bearer ***
```

响应：
```json
{"msg": "ok"}
```

### 文件上传
```
POST /api/v1/chat/upload
Authorization: Bearer ***
Content-Type: multipart/form-data
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | file | 是 | 上传的文件（字段名 `file`） |

响应：
```json
{"url": "https://luois-james.xyz/static/abc123.txt"}
```

**文件 AI 解析**：将返回的 URL 作为消息文本发送到 `/send`，后端会自动读取文件内容并嵌入 prompt。

**支持的文件类型**：

| 类型 | 格式 | 说明 |
|------|------|------|
| 文本文件 | .txt .md .py .js .json .csv 等 30+ 格式 | 读取文本内容用于对话 |
| 图片文件 | .jpg .jpeg .png .gif .webp .bmp | 支持视觉分析（Vision），AI 可识别图片中的文字、物体、场景等内容 |

图片上传后可用于视觉问答：上传图片获取 URL，将 URL 作为消息文本发送到 `/send`，系统自动启用视觉模型进行解析。

### 访问静态文件
```
GET /static/{filename}
```
无需鉴权，直接访问上传的文件。

---

## 4. 语音评测

### 获取评测文本
```
GET /api/v1/voice/text
Authorization: Bearer ***
```

响应：
```json
{"text": "The early morning sun cast long shadows across the quiet street."}
```

注：文本由 LLM 随机生成，LLM 不可用时使用内置备用句库。

### 提交音频评测
```
POST /api/v1/voice/assess
Authorization: Bearer ***
Content-Type: application/json
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| audio | string | 是 | base64 编码的音频（WAV/PCM, 16kHz, 16bit, 单声道） |
| text | string | 是 | 评测参考文本 |

请求：
```json
{
    "audio": "UklGRiQAAAB...",
    "text": "Hello world"
}
```

响应：
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
        {"content": "hello", "score": 90, "status": "good"},
        {"content": "world", "score": 84, "status": "good"}
    ]
}
```

| 字段 | 说明 |
|------|------|
| score | 总分（0-100） |
| comment | 评语（根据分数自动生成） |
| dimensions | 四个维度分（准确度/流利度/完整度/标准度） |
| words | 逐词评分，status: good(>=80)/medium(60-79)/poor(<60) |

---

## 5. 语音对话

### 语音聊天（流式）
```
POST /api/v1/voice/chat
Authorization: Bearer ***
Content-Type: application/json
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| audio | string | 是 | base64 编码的音频（WAV/PCM, 16kHz, 16bit, 单声道） |
| conversation_id | int | 否 | 不传则新建语音对话 |

请求：
```json
{
    "audio": "UklGRiQAAAB...",
    "conversation_id": null
}
```

**流式响应**（SSE 分块传输）：

后端先将音频转文字（ASR），再调用 LLM 生成回复。流中逐块返回 AI 回复文本，最后以 META 行结束：

```
你好！
我也觉得今天天气不错……
__META__{"conversation_id":2,"reply":"我也觉得今天天气不错……","title":"闲聊","image_url":""}
```

META 格式与文字聊天 `/send` 一致，包含 `conversation_id`、`reply`、`title`、`image_url` 字段。

> 注：语音对话与文字对话共用同一套 conversation，可在文字聊天历史中查看语音对话记录。

### 语音对话历史
```
GET /api/v1/voice/history?limit=20&before=1712345678000
Authorization: Bearer ***
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| limit | int | 否 | 每页条数，默认 20，最大 100 |
| before | int | 否 | 毫秒时间戳，加载更早记录 |

响应：
```json
[
    {
        "id": 1,
        "conversation_id": 2,
        "user_text": "今天天气怎么样",
        "ai_reply": "今天天气不错，适合出门走走。",
        "audio_url": "https://luois-james.xyz/static/voice/xxx.wav",
        "created_at": "2026-07-22 14:30:00"
    }
]
```

| 字段 | 说明 |
|------|------|
| id | 语音记录 ID |
| conversation_id | 关联对话 ID |
| user_text | ASR 识别后的用户文本 |
| ai_reply | AI 文字回复 |
| audio_url | 用户原始音频文件 URL |
| created_at | 创建时间 |

---

## 6. 健康检查

```
GET /health  →  {"status": "ok"}
GET /        →  {"service": "AI Chat Server", "version": "1.0"}
```
无需鉴权。

---

## 管理后台 API

> 管理员通过 `/admin` 页面登录后使用，所有端点需 `Authorization: Bearer <token>` 头

### 登录
```
POST /api/v1/admin/login
Body: {"password": "xxx"}
→ {"token": "..."}
```

### 用户管理
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/admin/stats` | GET | 系统统计（用户数、对话数等） |
| `/api/v1/admin/users?page=1&limit=20&search=xxx` | GET | 用户列表 |
| `/api/v1/admin/users/{id}` | GET | 用户详情（含统计数据） |
| `/api/v1/admin/users/{id}` | PUT | 更新用户（nickname/phone/avatar_url） |
| `/api/v1/admin/users/{id}` | DELETE | 删除用户（级联清除所有数据） |

### 用户数据管理
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/admin/users/{id}/conversations` | GET | 用户的对话列表 |
| `/api/v1/admin/conversations/{cid}/messages?limit=200` | GET | 查看对话消息 |
| `/api/v1/admin/conversations/{cid}` | DELETE | 删除对话（清理文件） |
| `/api/v1/admin/users/{id}/assessments` | GET | 用户评测记录 |
| `/api/v1/admin/assessments/{id}` | DELETE | 删除评测记录 |
| `/api/v1/admin/users/{id}/memories` | GET | AI 记忆 |
| `/api/v1/admin/memories/{id}` | DELETE | 删除记忆 |
| `/api/v1/admin/users/{id}/files` | GET | 上传文件列表 |
| `/api/v1/admin/files/{id}` | DELETE | 删除文件（清理磁盘） |

---

## 手机号绑定

```
POST /api/v1/user/bind-phone
Body: {"encrypted_data": "...", "iv": "..."}
→ {"msg": "ok", "phone": "138****8888"}
```
每个手机号只能绑定一个账号。

---

## 2026-07-28 更新

### 用户用量接口
```
GET /api/v1/user/usage
→ {"usage": {"chat": 5, "voice_assess": 1}, "limits": {"chat": 20, ...}, "role": "user", "vip_expires_at": null}
```
返回当日用量、限额、会员状态和到期时间。

### 管理后台 VIP 管理
```
PUT /api/v1/admin/users/{id}
Body: {"role": "vip", "vip_days": 30}   # 设 VIP 30 天
Body: {"role": "vip", "vip_days": -1}   # 永久
Body: {"role": "user"}                  # 取消
```

### 管理后台用量查询
```
GET /api/v1/admin/users/{id}/usage?days=7
→ [{"metric": "chat", "total": 15}, ...]
```
