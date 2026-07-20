# 语音评测功能开发日志

## 概述
将讯飞语音评测（ISE）流式 WebSocket API 集成到 ZLWL 智能聊天微信小程序中，实现英语口语朗读评分功能，包括总分、准确度、流利度、完整度、标准度及逐词发音分析。

## 技术栈
- 讯飞 ISE API：评测引擎 en_vip，题型 read_sentence
- 传输协议：WebSocket 流式（wss://ise-api.xfyun.cn/v2/open-ise）
- 音频规格：16kHz 采样率、16bit 位深、单声道、PCM raw
- 服务端：FastAPI + websockets，部署于 117.69.252.58:8080
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

## 部署命令
  cd /home/dfzz/wx-miniapp-ai/server
  nohup python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8080 > logs/uvicorn.log 2>&1 &
  curl http://127.0.0.1:8080/health

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
