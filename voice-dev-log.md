# 语音评测功能开发日志

## 概述
将讯飞语音评测（ISE）流式 WebSocket API 集成到 ZLWL 智能聊天微信小程序中，实现英语口语朗读评分功能，包括总分、准确度、流利度、完整度、标准度及逐词发音分析。

## 技术栈
- 讯飞 ISE API：评测引擎 en_vip，题型 read_sentence
- 传输协议：WebSocket 流式（wss://ise-api.xfyun.cn/v2/open-ise）
- 音频规格：16kHz 采样率、16bit 位深、单声道、PCM raw
- 服务端：FastAPI + websockets，部署于 47.116.193.74:8000
- 前端：微信小程序原生框架，wx.request + base64 传输音频
- 域名：https://luois-james.xyz（Cloudflare Tunnel 代理）

## 核心文件

### 后端
| 文件 | 作用 |
|------|------|
| app/utils/xf_ise.py | ISE WebSocket 客户端：鉴权签名、SSB/TTP/AUW 协议、XML 解析 |
| app/routers/voice.py | 两个接口：GET /voice/text（获取评测文本）、POST /voice/assess（接收音频+文本，调用 ISE） |
| app/config.py | 讯飞 AppID/APIKey/APISecret 配置 |

### 前端
| 文件 | 作用 |
|------|------|
| pages/voice/voice.js | 录音管理、音频 base64 编码、wx.request 提交、结果归一化 |
| pages/voice/voice.wxml | UI 布局：录音按钮、评分面板、逐词分析、颜色图例 |
| pages/voice/voice.wxss | 样式：分数进度条、词卡三档着色（绿/黄/红） |
| app.json | scope.record 录音权限声明 |

## 关键技术问题及解决

### 1. 鉴权 401/403
- 现象：WebSocket 连接被拒绝
- 原因：URL 参数中 host/path 未正确 URL 编码，HMAC-SHA256 签名计算时 date 格式不对
- 解决：使用 urllib.parse.quote 编码 host 和 path，date 严格使用 RFC 1123 格式

### 2. 试题格式错误 (code 48195)
- 现象：SSB 帧中使用 ttp_skip: true 直接带文本 base64 始终返回 48195
- 解决：放弃 ttp_skip 模式，改用手动 TTP 独立帧单独发送文本
- 踩坑：初始使用 status: 2 导致 ISE 服务端 panic（runtime error: index out of range），改为 status: 0 后正常

### 3. 超时 (code 60114)
- 现象：发送音频后 ISE 一直等待，最终超时
- 原因：未发送音频结束帧，ISE 不知道数据传输完毕
- 解决：所有 AUW 数据帧发送完后，必须显式发送结束帧（aus: 4, status: 2, data: 空）
- 音频分帧 base64 长度控制在 26000 以内，每个 chunk 发送后 sleep 对应时长模拟实时流式

### 4. 文本格式
- 最终：BOM 头（U+FEFF）+ 纯文本原文，无需 [content] 标记
- 早期尝试 [content] 标记导致 48195 或解析异常

### 5. XML 结果解析
- 现象：解析到 0 分，实际 XML 中有分数
- 原因：代码按 read_sentence > read_chapter 结构硬编码查找节点，但实际结果在 rec_paper > read_chapter 内
- 解决：遍历所有节点，找第一个带 total_score 属性的节点。分数 0-5 分制，自动 x20 转为百分制
- 维度分来源：accuracy（准确度）、fluency（流利度）、integrity（完整度）、standard（标准度）

### 6. 完整度评分极低
- 现象：完整朗读但完整度仅 60 分，后半部分单词缺失
- 原因：xf_ise.py 中有两处 PCM 硬截断，导致录音后半段被丢弃
- 解决：移除所有硬截断限制，完整音频上送 ISE

### 7. 前端传输方式
- 初始：wx.uploadFile multipart/form-data
- 问题：真机 uploadFile 域名限制，Form 解析不稳定
- 最终：wx.getFileSystemManager().readFile 转 base64 -> wx.request JSON 发送

### 8. 逐词分析着色
- 问题：ISE 返回的 dp_message 字段在 read_sentence 模式下始终为 0（ok），所有单词同色
- 解决：改为按单词分数分档着色
  - >=80：绿色（good）发音优秀
  - 60-79：黄色（medium）发音一般
  - <60：红色（poor）需加强
- 过滤 ISE 内部标记 sil（静音）和 fil（填充）

### 9. 录音权限
app.json 添加 permission.scope.record 声明，voice.js 增加 wx.getSetting 前置检查

## 正确调用示例

### 协议总览（三步帧序列）

讯飞 ISE 流式版使用 WebSocket 通信，必须严格按以下顺序发送帧：

```
客户端                            ISE 服务端
  |                                      |
  |-- 帧1: SSB（参数协商） ----------->  |
  |  <--------- {code: 0} -------------  |
  |                                      |
  |-- 帧2: TTP（评测文本） ----------->  |
  |  <--------- {code: 0} -------------  |
  |                                      |
  |-- 帧3: AUW aus=1（音频首帧） ------>  |
  |-- 帧4: AUW aus=2（音频中间帧） ---->  |
  |  ...                                 |
  |-- 帧N: AUW aus=4 status=2（结束）-->  |
  |                                      |
  |  <--------- {code: 0, data: XML} ---  |
  |  <--------- {code: 0, status: 2} ---  |
```

### 帧1: SSB（参数协商）

```json
{
  "common": { "app_id": "<必填> 讯飞控制台应用ID" },
  "business": {
    "sub":  "ise",     // 【必填】固定为 "ise"
    "cmd":  "ssb",     // 【必填】固定为 "ssb"
    "ent":  "en_vip",  // 【必填】评测引擎：en_vip(英语), zh_cn(中文)
    "category": "read_sentence", // 【必填】题型
    "aue":  "raw",     // 【必填】音频编码：raw/speex/speex-wb/icodec/opus
    "auf":  "audio/L16;rate=16000" // 【必填】L16=16bit, rate=采样率
  },
  "data": { "status": 0 }  // 【必填】
}
```

#### SSB business 参数速查

| 参数 | 必填 | 说明 | 可选值 |
|------|------|------|--------|
| cmd | **是** | 固定 | `"ssb"` |
| sub | **是** | 固定 | `"ise"` |
| ent | **是** | 评测引擎 | `en_vip` 英语, `zh_cn` 中文 |
| category | **是** | 题型 | `read_sentence` 句子, `read_word` 单词, `read_chapter` 篇章, `sentence` 自由说 |
| aue | **是** | 音频编码 | `raw` 推荐(PCM), `speex`, `speex-wb`, `icodec`, `opus` |
| auf | **是** | 音频参数 | `audio/L16;rate=16000`(16kHz 16bit), `audio/L16;rate=8000`(8kHz) |
| rst | 否 | 返回格式 | `plain` 明文(默认), `json` |
| rse | 否 | 多候选 | `utf8` 启用 |
| plev | 否 | 详细程度 | `0` 简单, `1` 详细(含音节/音素) |
| ise_unite | 否 | 综合评分 | `1` 启用 |
| ttp_skip | 否 | 跳过TTP | **强烈不建议**（实测反复 48195） |

### 帧2: TTP（评测文本）— 必发送

```json
{
  "business": { "sub": "ise", "cmd": "ttp" },
  "data": {
    "status": 0,           // 【关键】必须为 0！status=2 会导致 ISE panic
    "data": "<base64(U+FEFF + 文本内容)>"  // BOM头 + 纯文本
  }
}
```

**文本编码规则**：
- BOM 头 `﻿` + 原文，整体 base64 编码
- 不要加 `[content]` 标记 → 48195 错误
- 示例：`base64.b64encode(('﻿' + 'Hello world').encode()).decode()`

### 帧3+: AUW（音频上传）

音频分帧规则：
- 每个 chunk 的 base64 长度 ≤ 26000
- chunk 间 sleep 模拟实时流：`sleep(len(chunk)*3/4/32000)`
- 帧类型：

| 帧 | aus | status | data | 说明 |
|----|-----|--------|------|------|
| 首帧 | 1 | 0 | chunk_base64 | 第一块音频 |
| 中间帧 | 2 | 1 | chunk_base64 | 后续音频 |
| 结束帧 | 4 | 2 | "" (空串) | **必须发送！否则 ISE 等待→60114 超时** |

```json
// 首帧
{"business": {"sub":"ise","cmd":"auw","aus":1}, "data": {"status":0,"data":"<chunk1>"}}
// 中间帧
{"business": {"sub":"ise","cmd":"auw","aus":2}, "data": {"status":1,"data":"<chunk2>"}}
// 结束帧（必须！）
{"business": {"sub":"ise","cmd":"auw","aus":4}, "data": {"status":2,"data":""}}
```

### 音频规格要求

| 参数 | 要求 |
|------|------|
| 采样率 | 16000 Hz（推荐）或 8000 Hz |
| 位深 | 16 bit |
| 声道 | 单声道（mono） |
| 格式 | PCM raw（无头，需从 WAV 剥离 44 字节头） |
| 编码 | 转 base64 上传 |
| 时长 | ≤ 60 秒 |

WAV 转 PCM 注意：兼容含 LIST/FACT 等附加块的 WAV，需扫描查找 `data` chunk 而非固定偏移。

### 结果 XML 结构

```xml
<xml_result>
  <read_sentence lan="en" type="study" version="7.0">
    <rec_paper>
      <read_chapter total_score="4.35" accuracy_score="4.45" fluency_score="4.30"
                    integrity_score="5.00" standard_score="3.75">
        <word content="the" total_score="4.05" dp_message="0">
          <syll content="dh ax" syll_score="3.20" serr_msg="0">
            <phone content="dh" dp_message="0" perr_msg="0" is_yun="0"/>
            <phone content="ax" dp_message="0" perr_msg="0" is_yun="0"/>
          </syll>
        </word>
        <!-- 更多单词... -->
      </read_chapter>
    </rec_paper>
  </read_sentence>
</xml_result>
```

**解析要点**：
- 遍历查找第一个带 `total_score` 属性的节点（不按结构硬编码路径）
- 分数 0-5 分制，需 ×20 转百分制
- `dp_message`：0=正确, 16=漏读, 32=多读, 64=重复, 128=替换（但 `read_sentence` 模式固定返回 0，需改按分数分档评价）

### 鉴权签名（HMAC-SHA256）

```python
import base64, hashlib, hmac, datetime
from urllib.parse import quote

def build_auth_url(api_key, api_secret, host="ise-api.xfyun.cn", path="/v2/open-ise"):
    now = datetime.datetime.utcnow()
    date = now.strftime("%a, %d %b %Y %H:%M:%S GMT")  # RFC 1123 格式
    
    sig_origin = f"host: {host}\ndate: {date}\nGET {path} HTTP/1.1"
    signature = base64.b64encode(
        hmac.new(api_secret.encode(), sig_origin.encode(), hashlib.sha256).digest()
    ).decode()
    
    auth = f'api_key="{api_key}",algorithm="hmac-sha256",headers="host date request-line",signature="{signature}"'
    authorization = base64.b64encode(auth.encode()).decode()
    
    return f"wss://{host}{path}?authorization={quote(authorization)}&date={quote(date)}&host={quote(host)}"
```

**关键**：`authorization` 和 `date` 必须 `urllib.parse.quote` 编码，否则 URL 中特殊字符 → 401/403。

### 常见错误码速查

| 错误码 | 含义 | 根因与解决 |
|--------|------|-----------|
| 401 | 未授权 | API Key/Secret 错误或签名计算有误 |
| 403 | 禁止访问 | URL 参数未做 url encode |
| 48195 | 试题格式错误 | 文本格式不对（不要加 `[content]`！）或 ttp_skip 模式异常 |
| 60114 | 超时 | **未发送 AUW 结束帧** `aus=4, status=2` |
| 10163 | 音频过短 | 音频数据不足，检查分帧逻辑 |
| 10165 | 音频过长 | 单次评测不超过 60 秒 |
| 11200 | 服务内部错误 | TTP 帧 status 误用了 2 而非 0 导致 panic |

### 完整调用示例（Python）

```python
import asyncio, base64, json
import websockets

async def ise_assess(pcm_bytes: bytes, text: str, app_id: str, api_key: str, api_secret: str):
    # 1. 鉴权 URL
    url = build_auth_url(api_key, api_secret)
    
    # 2. 文本编码：BOM + base64
    text_b64 = base64.b64encode(("\ufeff" + text).encode()).decode()
    
    # 3. 音频分帧（chunk base64 < 26000）
    CHUNK = 19000  # raw bytes per chunk
    chunks = [base64.b64encode(pcm_bytes[i:i+CHUNK]).decode() for i in range(0, len(pcm_bytes), CHUNK)]
    
    async with websockets.connect(url, ping_interval=15, close_timeout=120) as ws:
        # 帧1: SSB
        await ws.send(json.dumps({
            "common": {"app_id": app_id},
            "business": {"sub":"ise","cmd":"ssb","ent":"en_vip","category":"read_sentence",
                         "aue":"raw","auf":"audio/L16;rate=16000"},
            "data": {"status": 0}
        }))
        r = json.loads(await ws.recv())
        if r.get("code") != 0: raise Exception(f"SSB fail: {r}")
        
        # 帧2: TTP
        await ws.send(json.dumps({
            "business": {"sub":"ise","cmd":"ttp"},
            "data": {"status": 0, "data": text_b64}
        }))
        r = json.loads(await ws.recv())
        if r.get("code") != 0: raise Exception(f"TTP fail: {r}")
        
        # 帧3+: AUW
        for i, chunk in enumerate(chunks):
            await asyncio.sleep(len(chunk) * 3 / 4 / 32000)
            aus = 1 if i == 0 else 2
            st = 0 if i == 0 else 1
            await ws.send(json.dumps({
                "business": {"sub":"ise","cmd":"auw","aus": aus},
                "data": {"status": st, "data": chunk}
            }))
        # 结束帧（必须！）
        await ws.send(json.dumps({
            "business": {"sub":"ise","cmd":"auw","aus": 4},
            "data": {"status": 2, "data": ""}
        }))
        
        # 4. 接收结果
        result = None
        async for msg in ws:
            data = json.loads(msg)
            if data.get("code", -1) != 0:
                raise Exception(f"ISE error: code={data.get('code')} msg={data.get('message')}")
            raw = data.get("data", {}).get("data", "")
            if raw:
                result = base64.b64decode(raw).decode()  # XML 字符串
            if data.get("data", {}).get("status", 0) == 2:
                break
        return result  # 返回 XML，需自行解析

# 调用
xml = asyncio.run(ise_assess(
    pcm_data, "Hello world", "<app_id>", "<api_key>", "<api_secret>"
))
```

## 部署命令
  cd /opt/wx-miniapp-ai/server
  nohup python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > logs/uvicorn.log 2>&1 &
  curl http://127.0.0.1:8000/health

## 当前状态
- 讯飞 ISE 协议完全跑通，评测结果正常返回
- PCM 截断已移除，完整度评分恢复正常
- 逐词分析按分数三档着色 + 图例说明
- 前端 USE_MOCK = false，使用真实评测
- 录音最长 30 秒

## 已知限制
- 仅支持 read_sentence 题型，暂未扩展 read_word、read_chapter 等
- ISE dp_message 字段在句子模式不区分漏读/错读/多读

## 待优化
- 前端录音增加倒计时/预加载缓冲，避免开头截断
- 评测历史记录与趋势图表
- 正式环境关闭 DEV_SKIP_LOGIN


---

## 2026-07-21 工作记录

### 文件上传 AI 解析
- **问题**：用户发文件给 AI，AI 收到的是 URL 字符串无法访问，回复"无法打开外部链接"
- **解决**：后端 `/send` 接口新增 `_resolve_file_message()` 函数
  - 检测 `https://luois-james.xyz/static/` 前缀的 URL
  - 文本文件（.txt/.md/.py/.json 等 30+ 格式）：自动读取内容嵌入 LLM prompt
  - 图片文件：告知 AI 不可查看
  - 二进制文件：告知不可读取
  - 超 6000 字符自动截断
- **前端优化**：文件气泡显示原始文件名（如 `report.txt`），而非裸 URL

### 逐词分析着色优化
- **问题**：ISE 返回 dp_message 始终为 0，所有单词显示同一颜色
- **解决**：改为按单词分数三档着色
  - >=80 分：绿色（good）— 发音优秀
  - 60-79 分：黄色（medium）— 一般
  - <60 分：红色（poor）— 需加强
- 过滤 ISE 内部标记 `sil`（静音）和 `fil`（填充）
- 新增颜色图例说明

### 服务器迁移（117.69.252.58 → 47.116.193.74）
- **新服务器**：阿里云 ECS（Alinux 4），Python 3.11
  - IP: `47.116.193.74`
  - 用户: `root`
  - 代码路径: `/opt/wx-miniapp-ai`
  - uvicorn 端口: `8000`
- **ICP 备案问题**：阿里云拦截未备案域名 HTTP 流量
- **解决方案**：部署 Cloudflare Tunnel
  - 从旧服务器复制 cloudflared 二进制和认证证书
  - 创建 systemd 服务（开机自启）
  - 配置 ingress: `luois-james.xyz → http://127.0.0.1:8000`
  - DNS 改为 CNAME 指向 `626935f4-...cfargotunnel.com`
  - SSL/TLS 模式设为 Full
  - 关闭 Nginx（不再需要），tunnel 直连 uvicorn
- **git 配置**：生成 SSH key，添加 GitHub 授权，仓库同步

### 当前架构

```
用户 → Cloudflare CDN → Tunnel → 47.116.193.74:8000 (uvicorn)
                                  ↑ cloudflared systemd
                                  域名 luois-james.xyz
                                  SSL: Cloudflare 边缘终止
```


### OpenClaw 智能体网关集成
- **背景**：原直接调用 DeepSeek API，无法利用本地 OpenClaw 网关的智能体能力
- **架构**：`_call_llm()` 统一调用入口
  - 优先：OpenClaw Gateway（`http://127.0.0.1:12178/v1`）
  - 备用：直连 DeepSeek API（`https://api.deepseek.com/v1`）
  - 切换逻辑：检测 `OPENCLAW_TOKEN` 环境变量，有则走网关，无或失败则 fallback DeepSeek
- **配置**（`.env`）：
  - `OPENCLAW_URL` — 网关地址，默认 `http://127.0.0.1:12178/v1`
  - `OPENCLAW_TOKEN` — 网关认证 token
  - `OPENCLAW_MODEL` — 模型名，默认 `openclaw`

### 记忆管理系统
- **新增文件**：`server/app/utils/memory_manager.py`
- **功能**：
  - 用户记忆存储（`user_memories` 表）：content、importance、key
  - `build_context(uid)` — 构建对话上下文，注入 system prompt
    - 优先级：档案摘要 > 高重要度事实 > 近期事实
    - 预算控制：摘要 300 字 + 事实 500 字 = 总 800 字
  - `maybe_compress(uid)` — 活跃记忆超 12 条时，调用 LLM 压缩为摘要
  - 自动增减重要性分数
- **集成**：`chat()` 和 `gen_title()` 接收 `uid` 参数，调用时自动注入记忆上下文

### 提交记录
- 后端 GitHub: `11f53eb` — 服务器适配 + 文件AI解析 + 记忆管理 (8 files)
- 前端 微信 git: `1c7fae9` — 逐词着色 + 文件显示 + 配置更新
- 后端 GitHub: `ab2acaa` — 开发日志更新

### 提交记录
- 后端 GitHub: `11f53eb` — 服务器适配 + 文件AI解析 + 记忆管理 (8 files)
- 前端 微信 git: `1c7fae9` — 逐词着色 + 文件显示 + 配置更新


---

## 2026-07-21 后续工作记录

### 一、服务器迁移与 Cloudflare Tunnel

**问题**：新服务器（阿里云 ECS 47.116.193.74）未备案，阿里云拦截 HTTP 流量返回 ICP 备案页。

**解决**：
- 从旧服务器（117.69.252.58）复制 cloudflared 二进制和 cert.pem
- 修改 config.yml 将 ingress 指向 `http://127.0.0.1:8000`
- 创建 systemd 服务（`/etc/systemd/system/cloudflared.service`）
- DNS 改为 CNAME → `626935f4-...cfargotunnel.com`（橙色代理）
- SSL/TLS 设为 Full 模式
- 停用 Nginx，tunnel 直连 uvicorn

**架构**：
```
用户 → Cloudflare CDN → Tunnel → 47.116.193.74:8000 (uvicorn)
                                  ↑ cloudflared systemd 自启
```

### 二、真流式输出

**问题**：后端 `/send` 用 `await llm_chat()` 等完整回复后一次性返回，前端虽支持 SSE 但实际不是流式。

**解决**：
- `llm_client.py` 新增 `_call_llm_stream()`：调用 DeepSeek/OpenClaw 时加 `stream: true`，逐 token 解析 SSE 事件并 `yield`
- `llm_client.py` 新增 `chat_stream()`：注入记忆上下文后调用流式函数
- `chat.py` `/send` 用 `StreamingResponse(generate())` 逐 token 推送到前端
- 末尾附带 `__META__` JSON 元数据（conversation_id、title）
- `chat.js` 适配：`onText` 过滤 `__META__` 显示纯文本，`.then()` 解析元数据

**效果**：前端逐字实时渲染，不再等完整回复。

### 三、Markdown 渲染

**问题**：AI 回复的 `**加粗**`、`

` 换行、列表等在前端当纯文本显示。

**解决**：
- 新建 `utils/markdown.js` — 正则转换器，支持：加粗、斜体、标题（#/##/###）、列表（-/1.）、分割线、行内代码、代码块、表格、引用块
- `message-bubble.wxml`：AI 消息改用 `<rich-text nodes="{{mdHtml}}">`
- `message-bubble.js`：`content` observer 自动解析，流式时 80ms 节流
- 代码块：黑底绿字配色（`#2d2d2d` 背景）
- 表格：完整的 `<table>/<tr>/<th>/<td>` 渲染

### 四、消息操作按钮

AI 气泡下方加 **📋 复制** / **↗️ 分享**，用户气泡下方加 **✏️ 编辑**。

- `message-bubble.wxml`：非流式、非失败、非图片/文件时显示按钮行
- `message-bubble.js`：`onCopy`/`onShare` 调 `wx.setClipboardData`
- `onEdit` → `triggerEvent('edit')` → `chat.js onEditMessage` → 回填输入框
- `chat-input.js` 新增 `editText` property observer，接收外部文字

### 五、批量删除消息

**问题**：长按消息弹 actionSheet 只能单条删除。

**解决**：
- **后端**：`message.py` 新增 `delete_by_ids(cid, ids)` → `DELETE FROM messages WHERE id IN (...)`
- **后端**：`chat.py` 新增 `DELETE /conversations/{cid}/messages` 接口
- **前端**：长按进入选择模式 → 点击气泡勾选 → 底部栏显示 `已选 N 条` → `取消` / `🗑 删除`
- `message-bubble.wxml`：选择模式下显示圆形 checkbox
- 删除时前端先移除 → 后端同步删除

### 六、会话重命名/删除同步

**问题**：重命名是乐观更新（先改 UI 再调后端），失败时 UI 不一致且静默吞错。

**解决**：
- 重命名：`PUT /conversations/{id}` 后端确认后 → 更新列表，失败 Toast 提示
- 删除会话：DB CASCADE 自动删关联消息，`.catch` 改为 Toast 而非静默吞错

### 七、个人中心增强

新增四个模块：

| 模块 | 后端 | 前端 |
|------|------|------|
| 📊 统计卡片 | `GET /api/v1/chat/stats`（对话数/消息数/评测数） | `profile.wxml` 三列数字卡片 |
| 🎯 评测记录 | `voice_assessments` 表 + `GET /voice/history` | 可展开面板，分数/文本/四维度 |
| 🧠 AI 记忆 | `GET/POST/DELETE /chat/memories`（已有接口） | 可展开面板，逐条显示 + ×删除 |
| ℹ️ 关于 | - | `wx.showModal` 弹版本号 |

**Bug**：stats 接口返回 500 → `stats.py` 函数名 `get_user_stats` 与 router 调用的 `user_stats` 不匹配，修复后正常。

### 八、头像上传与展示

**问题**：`wx.chooseAvatar` 返回临时 `wxfile://` 路径，存到 DB 后过期无法显示。

**解决**：
- `profile.js` `saveProfile()`：先 `wx.uploadFile` 上传头像到服务器 → 拿到永久 URL → 再 `PUT /user/profile` 存入 DB
- `chat.js` `loadUserAvatar()`：从 `globalData.userInfo.avatarUrl` 读取
- `message-bubble.wxml`：用户头像有 URL 用 `<image>`，无则默认 😀
- CSS：`avatar-user` 加 `overflow:hidden`，`avatar-img` 圆形裁切

### 九、视觉模型图片识别

**问题**：用户发图片后 AI 说"无法查看"。

**解决**：
- `llm_client.py` 新增 `_has_image()` / `_describe_images()` / `_vision_call()`
- 通过 OpenRouter 调用 `qwen/qwen3-vl-235b-a22b-instruct` 视觉模型
- `chat()` / `chat_stream()` 自动检测 `image_url` 类型消息并预处理
- `chat.py` `_resolve_file_message()`：检测到图片 URL → `await _vision_call(url)` 获取描述 → 嵌入 prompt
- 配置：`.env` 中 `OPENROUTER_KEY` + `VISION_MODEL=qwen/qwen3-vl-235b-a22b-instruct`

**Bug**：视觉模型 18 秒响应，前端 60 秒超时足够。但 `kill -HUP` 无法热重载 uvicorn，需 `kill -9` + 重启。

### 十、图片历史记录类型检测

**问题**：上传的图片在聊天记录中显示为一串 URL 文本而非图片。

**解决**：`chat.js` 新增 `detectMessageType(content)` 函数，加载历史消息时自动检测：
- `https://luois-james.xyz/static/xxx.jpg` → `type: 'image'` → 气泡显示图片
- `https://luois-james.xyz/static/xxx.pdf` → `type: 'file'` → 气泡显示文件卡片
- 其他 → 纯文本

### 十一、清理聊天双重确认

**问题**：清除所有聊天记录只需点一次确认，容易误操作。

**解决**：两步确认：
1. 弹窗 "⚠️ 此操作不可恢复" → 点"继续"
2. 弹窗输入框 → 输入"确认删除"四个字 → 不匹配则取消

### 当前技术栈全景

```
前端：微信原生小程序（wx.request/uploadFile/rich-text）
后端：FastAPI + uvicorn + MariaDB
AI：OpenClaw Gateway → DeepSeek（流式）
视觉：OpenRouter → qwen3-vl
语音评测：讯飞 ISE WebSocket API
语音对话：Qwen3.5-Omni-Flash（音频→文本）+ Qwen3-TTS-Flash（文本→语音）
传输：Cloudflare Tunnel（绕过 ICP 备案）
代码：GitHub byOpenClaw 分支 + 微信 git Test 分支
```


---

## 2026-07-22 工作记录

### 口语对练（Qwen-Omni 多模态）

#### 概述
集成阿里云 DashScope 的 Qwen-Omni 多模态模型，实现微信小程序内的实时语音对话功能。
用户录音 → 服务端语音识别 → LLM 对话 → TTS 合成 → 前端播放，形成完整的语音交互闭环。

#### 技术选型

| 能力 | 模型 | 说明 |
|------|------|------|
| 语音识别（ASR） | **Qwen3.5-Omni-Flash** | 多模态模型，支持音频输入 → 文本输出 |
| 语音合成（TTS） | **Qwen3-TTS-Flash** | 文本转语音，支持多种音色和语速控制 |
| LLM 对话 | DeepSeek（通过 OpenClaw Gateway） | 流式文本对话 |

#### 为什么选择 HTTP 模式而非 WebSocket Realtime

DashScope 提供两种 Qwen-Omni 接入方式：
1. **WebSocket Realtime API** — 低延迟双向流式，但协议复杂，需管理连接生命周期
2. **HTTP REST API** — 请求-响应模式，简单可靠

**选择 HTTP 的原因**：
- 微信小程序端网络环境不稳定，WebSocket 长连接容易断开
- HTTP 模式更易调试和错误处理
- 延迟差异在小程序场景下可接受（HTTP 往返 ~1-2s vs WebSocket ~0.5s）
- 无需处理复杂的 WebSocket 重连逻辑
- Dashboard 的 HTTP API 已足够稳定，支持流式响应

#### 语音识别（Qwen3.5-Omni-Flash）

**调用方式**：HTTP POST multipart/form-data 上传音频文件

```
POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
Authorization: Bearer <DASHSCOPE_API_KEY>
Content-Type: multipart/form-data

- model: qwen3.5-omni-flash
- messages: [{"role": "user", "content": [{"type": "audio", "audio": <audio_file>}]}]
```

**处理流程**：
1. 前端录音（16kHz, 16bit, mono PCM）
2. 上传到后端 /speak/asr 接口
3. 后端调用 Qwen-Omni，传入 "请将这段音频转写为文字，只输出文本"
4. 返回识别文本，同时将该文本作为用户消息发给 LLM 对话
5. LLM 流式返回回复文本
6. 文本通过 TTS 合成语音返回前端

#### 语音合成（Qwen3-TTS-Flash）

**调用方式**：HTTP POST JSON

```
POST https://dashscope.aliyuncs.com/api/v1/services/aigc/text-to-speech/speech-synthesis
Authorization: Bearer <DASHSCOPE_API_KEY>

{
  "model": "qwen3-tts-flash",
  "input": {"text": "<要合成的文本>"},
  "parameters": {
    "voice": "Cherry",
    "speech_rate": 1.0
  }
}
```

**音色选择**：

| 音色 | 语言 | 风格 | 适用场景 |
|------|------|------|----------|
| Cherry | 中英 | 温柔知性女声 | 通用对话 |
| Kai | 中英 | 沉稳自然男声 | 对话/朗读 |
| Eric | 中英 | 自信有力男声 | 教学/演示 |

**语速控制**：支持 0.8x ~ 2.0x 范围调整
- 0.8x：慢速，适合英语学习跟读
- 1.0x：正常速度（默认）
- 1.2x-1.5x：稍快，适合日常对话
- 2.0x：快速，适合听力训练

#### 核心文件

| 文件 | 作用 |
|------|------|
| `app/utils/qwen_omni.py` | Qwen-Omni HTTP 客户端：ASR 识别、TTS 合成、音频格式处理 |
| `app/routers/speak.py` | 口语对练接口：`/speak/asr`（语音识别+对话）、`/speak/tts`（纯合成） |
| `pages/speak/` | 前端口语对练页面（speak.js/.wxml/.wxss） |
| `pages/speak/speak.js` | 录音管理、音频上传、语音播放、对话状态管理 |
| `pages/speak/speak.wxml` | UI：对话气泡、录音按钮、播放控件 |
| `pages/speak/speak.wxss` | 样式：聊天气泡、录音动画、播放指示器 |

#### 接口设计

**POST /speak/asr** — 语音识别 + 对话
- 输入：`audio`（multipart 音频文件）
- 输出：`{text, reply, audio}` — 识别文本 + LLM 回复文本 + TTS 音频 URL
- 流程：ASR → LLM 对话 → TTS 合成，三阶段流水线

**POST /speak/tts** — 纯文本转语音
- 输入：`{text, voice?, speed?}`
- 输出：`{audio_url}` — 合成的语音文件 URL

#### 音频处理

- 前端录音格式：MP3 或 WAV（微信原生录音）
- 后端自动转换为 Qwen-Omni 要求的格式（16kHz, mono）
- TTS 返回的音频缓存在服务器 static/tts/ 目录，定期清理

#### 关键技术问题及解决

**1. 音频格式兼容**
- 问题：微信录音为 MP3 格式，Qwen-Omni 要求 PCM/WAV
- 解决：后端使用 pydub + ffmpeg 将 MP3 转 PCM，统一 16kHz 单声道

**2. 前后端音频传输**
- 问题：微信小程序 wx.uploadFile 不支持 ArrayBuffer
- 解决：录音后通过 wx.getFileSystemManager 读为临时文件，直接 uploadFile 上传

**3. TTS 延迟优化**
- 问题：完整合成再返回导致等待时间长
- 解决：采用流式方案，LLM 逐句输出 → 立即 TTS 合成 → 边合成边返回音频片段

**4. 对话上下文管理**
- 问题：语音对话需要保持多轮上下文
- 解决：speak 接口复用 chat 模块的对话管理，自动关联 conversation_id

### 服务器迁移收尾

- Cloudflare Tunnel 稳定运行，systemd 开机自启验证通过
- 代码路径统一为 `/opt/wx-miniapp-ai`
- uvicorn 端口统一为 `8000`
- git 仓库配置完成，支持 push/pull
- 旧服务器（117.69.252.58）已停用，所有服务迁移至 47.116.193.74
