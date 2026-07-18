# 微信小程序 AI 智能体 — 服务端 API 文档

**Base URL**: `https://luois-james.xyz`

---

## 鉴权说明

所有需要登录的接口，需在 Header 中携带 Token：

```
Authorization: Bearer <token>
```

Token 通过 `/api/v1/auth/login` 获取。

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
| token | 登录凭证，72小时有效，后续请求携带 |
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
    "reply": "你好！我是你的AI智能助手，可以帮你解答问题、聊天、创作……",
    "title": "自我介绍"
}
```

| 字段 | 说明 |
|------|------|
| conversation_id | 对话ID，后续发消息时带上 |
| reply | AI 回复文本 |
| title | 仅新建对话时返回，AI 自动生成的对话标题 |

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

> 按 `updated_at` 倒序排列，最新的在前面。`msg_count` 为该对话的消息总数。

---

## 4. 加载对话历史

```
GET /api/v1/chat/conversations/{id}/messages
Authorization: Bearer <token>
```

响应：

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
        {"role": "assistant", "content": "你好！我是你的AI助手……"},
        {"role": "user", "content": "你能帮我做什么"},
        {"role": "assistant", "content": "我可以帮你……"}
    ]
}
```

| role 取值 | 含义 |
|-----------|------|
| user | 用户消息 |
| assistant | AI 回复 |

---

## 5. 删除对话

```
DELETE /api/v1/chat/conversations/{id}
Authorization: Bearer <token>
```

响应：

```json
{"msg": "ok"}
```

---

## 6. 退出登录

```
POST /api/v1/auth/logout
Authorization: Bearer <token>
```

响应：

```json
{"msg": "ok"}
```

---

## 7. 获取用户信息

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
    "avatar_url": "https://...",
    "phone": null,
    "created_at": "2026-07-16 09:00:00"
}
```

---

## 8. 更新用户资料

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
