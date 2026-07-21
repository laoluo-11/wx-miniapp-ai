# ZLWL 智能聊天 — API 文档

**Base URL**: `https://luois-james.xyz`
**API 前缀**: `/api/v1`

---

## 鉴权

除登录和静态文件外，所有接口需在 Header 携带 Token：

```
Authorization: Bearer <token>
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
    "token": "<JWT>",
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
Authorization: Bearer <token>
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
Authorization: Bearer <token>
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
Authorization: Bearer <token>
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
Authorization: Bearer <token>
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
```
你好！
你好！我是
你好！我是你的AI助手……
```

最终 JSON 结构：
```json
{
    "conversation_id": 1,
    "reply": "你好！我是你的AI助手……",
    "title": "自我介绍"
}
```

| 字段 | 说明 |
|------|------|
| conversation_id | 对话 ID |
| reply | AI 回复全文 |
| title | 仅新建对话返回，AI 自动生成标题 |

### 对话列表
```
GET /api/v1/chat/conversations
Authorization: Bearer <token>
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
Authorization: Bearer <token>
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
Authorization: Bearer <token>
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
Authorization: Bearer <token>
```

响应：
```json
{"msg": "ok"}
```

### 文件上传
```
POST /api/v1/chat/upload
Authorization: Bearer <token>
Content-Type: multipart/form-data
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | file | 是 | 上传的文件（字段名 `file`） |

响应：
```json
{"url": "https://luois-james.xyz/static/abc123.txt"}
```

**文件 AI 解析**：将返回的 URL 作为消息文本发送到 `/send`，后端会自动读取文本文件内容嵌入 prompt。支持 .txt .md .py .js .json .csv 等 30+ 格式。

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
Authorization: Bearer <token>
```

响应：
```json
{"text": "The early morning sun cast long shadows across the quiet street."}
```

注：文本由 LLM 随机生成，LLM 不可用时使用内置备用句库。

### 提交音频评测
```
POST /api/v1/voice/assess
Authorization: Bearer <token>
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

## 5. 健康检查

```
GET /health  →  {"status": "ok"}
GET /        →  {"service": "AI Chat Server", "version": "1.0"}
```
无需鉴权。
