# 微信小程序 AI 智能体 — 服务端 API 文档

**Base URL**: `https://luois-james.xyz`

---

## 鉴权说明

所有需要登录的接口，需在 Header 中携带 Token：

```
Authorization: Bearer <token>
```

Token 通过 `/api/v1/auth/login` 获取，有效期 72 小时。

---

## 通用错误格式

```json
{"message": "错误描述"}
```

常见状态码：

| 状态码 | 含义 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | Token 无效/过期 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

---

## 1. 微信登录

```
POST /api/v1/auth/login
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | string | 是 | `wx.login()` 返回的临时凭证 |

请求：

```json
{"code": "0b1xxxxx..."}
```

成功响应：

```json
{
    "token": "a1b2c3...",
    "user_id": 1,
    "openid": "oXXXX...",
    "is_new": true
}
```

| 字段 | 说明 |
|------|------|
| token | 登录凭证，72小时有效 |
| user_id | 用户ID |
| openid | 微信OpenID |
| is_new | 是否新用户（无昵称即为新用户） |

---

## 2. 发送消息（核心）

```
POST /api/v1/chat/send
Authorization: Bearer <token>
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| message | string | 是 | 用户输入的消息文本 |
| conversation_id | int | 否 | 不传=新建对话，传了=继续已有对话 |

请求：

```json
{
    "message": "你好，请介绍一下自己",
    "conversation_id": null
}
```

成功响应：

```json
{
    "conversation_id": 1,
    "reply": "你好！我是你的AI智能助手……",
    "title": "自我介绍"
}
```

| 字段 | 说明 |
|------|------|
| conversation_id | 对话ID |
| reply | AI 回复文本 |
| title | 仅新建对话时返回，AI 自动生成的标题；继续对话为 null |

---

## 3. 对话列表

```
GET /api/v1/chat/conversations
Authorization: Bearer <token>
```

响应：

```json
[
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

> 按 `updated_at` 倒序排列。`msg_count` 为该对话的消息总数。

---

## 4. 加载对话历史

```
GET /api/v1/chat/conversations/{id}/messages?limit=20&before=1712345678000
Authorization: Bearer <token>
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| limit | int | 否 | 每页条数，默认40，最大100 |
| before | int | 否 | 毫秒时间戳，加载此时间之前的更早消息 |

响应（扁平数组）：

```json
[
    {"role": "user", "content": "你好", "time": "2026-07-16 10:00:00"},
    {"role": "assistant", "content": "你好！我是你的AI助手……", "time": "2026-07-16 10:00:01"}
]
```

| 字段 | 说明 |
|------|------|
| role | `user` 或 `assistant` |
| content | 消息内容 |
| time | 发送时间 |

---

## 5. 重命名对话

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

---

## 6. 删除对话

```
DELETE /api/v1/chat/conversations/{id}
Authorization: Bearer <token>
```

响应：

```json
{"msg": "ok"}
```

---

## 7. 文件上传

```
POST /api/v1/chat/upload
Authorization: Bearer <token>
Content-Type: multipart/form-data
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | file | 是 | 上传的文件（图片/文档等） |

响应：

```json
{"url": "https://luois-james.xyz/static/abc123.jpg"}
```

---

## 8. 退出登录

```
POST /api/v1/auth/logout
Authorization: Bearer <token>
```

响应：

```json
{"msg": "ok"}
```

---

## 9. 获取用户信息

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
    "created_at": "2026-07-16 09:00:00"
}
```

---

## 10. 更新用户资料

```
PUT /api/v1/user/profile
Authorization: Bearer <token>
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| nickname | string | 否 | 用户昵称 |
| avatar_url | string | 否 | 头像URL |

请求：

```json
{"nickname": "新昵称", "avatar_url": "https://..."}
```

响应：

```json
{"msg": "ok"}
```

---

## 11. 语音测评

```
POST /api/v1/voice/assess
Authorization: Bearer <token>
Content-Type: multipart/form-data
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| audio | file | 是 | 录音文件（wav, 16kHz 单声道） |

响应：

```json
{
    "score": 85,
    "comment": "整体表现不错，注意连读与重音位置。",
    "dimensions": [
        {"name": "流利度", "score": 86},
        {"name": "发音", "score": 82},
        {"name": "准确度", "score": 84},
        {"name": "完整度", "score": 88}
    ]
}
```

---

## 健康检查

```
GET /health  →  {"status": "ok"}
GET /        →  {"service": "AI Chat Server", "version": "1.0"}
```
