"""
讯飞语音评测（流式版）ISE WebSocket 客户端
文档: https://www.xfyun.cn/doc/Ise/IseAPI.html
"""
import asyncio
import base64
import hashlib
import hmac
import json
import time
import struct
import datetime
from urllib.parse import quote
import websockets
from app.config import XF_API_KEY, XF_API_SECRET

ISE_HOST = "ise-api.xfyun.cn"
ISE_PATH = "/v2/open-ise"
ISE_URL = f"wss://{ISE_HOST}{ISE_PATH}"


def _build_auth_url():
    """生成带签名的 WebSocket URL"""
    now = datetime.datetime.utcnow()
    date = now.strftime("%a, %d %b %Y %H:%M:%S GMT")
    
    signature_origin = f"host: {ISE_HOST}\ndate: {date}\nGET {ISE_PATH} HTTP/1.1"
    signature = base64.b64encode(
        hmac.new(XF_API_SECRET.encode(), signature_origin.encode(), hashlib.sha256).digest()
    ).decode()
    
    auth_origin = f'api_key="{XF_API_KEY}",algorithm="hmac-sha256",headers="host date request-line",signature="{signature}"'
    authorization = base64.b64encode(auth_origin.encode()).decode()
    
    return (f"{ISE_URL}?authorization={quote(authorization)}&date={quote(date)}&host={quote(ISE_HOST)}")


def _wav_to_pcm(wav_bytes):
    """去除WAV头，提取原始PCM数据（兼容含LIST等附加块的WAV）"""
    if len(wav_bytes) < 12 or wav_bytes[:4] != b'RIFF' or wav_bytes[8:12] != b'WAVE':
        return wav_bytes
    # 跳过RIFF头（12 bytes），扫描所有块查找data块
    offset = 12
    while offset < len(wav_bytes) - 8:
        # chunk_id如果是非ASCII字节（如00），说明格式不对，跳过
        chunk_id = wav_bytes[offset:offset+4]
        chunk_size = struct.unpack('<I', wav_bytes[offset+4:offset+8])[0]
        if chunk_id == b'data':
            return wav_bytes[offset+8:offset+8+chunk_size]
        # 跳转到下一个块（块头8+块数据）
        step = 8 + chunk_size
        # 防止死循环：如果块大小为0或异常值，逐字节前进
        if step <= 8 or step > len(wav_bytes) - offset:
            offset += 1
        else:
            offset += step
    # 兜底：找不到data块，返回原数据
    return wav_bytes


def _parse_xml_result(xml_str):
    """解析XML评测结果"""
    import xml.etree.ElementTree as ET
    result = {"score": 0, "comment": "", "dimensions": [], "words": []}
    try:
        root = ET.fromstring(xml_str)
        # 找第一个有 total_score 属性的节点
        read_node = None
        for el in root.iter():
            if el.get("total_score"):
                read_node = el
                break
        if read_node is not None:
            total = float(read_node.get("total_score", 0))
            accuracy = float(read_node.get("accuracy_score", 0))
            fluency = float(read_node.get("fluency_score", 0))
            integrity = float(read_node.get("integrity_score", 0))
            standard = float(read_node.get("standard_score", 0))
            # 0-5分制转0-100
            if total < 10:
                total *= 20
                accuracy *= 20
                fluency *= 20
                integrity *= 20
                standard *= 20
            result["score"] = round(total)
            result["dimensions"] = [
                {"name": "准确度", "score": round(accuracy)},
                {"name": "流利度", "score": round(fluency)},
                {"name": "完整度", "score": round(integrity)},
                {"name": "标准度", "score": round(standard)},
            ]
            # 单词分析
            words = []
            for word_node in read_node.iter("word"):
                content = word_node.get("content", "")
                ws = float(word_node.get("total_score", 0))
                if ws < 10:
                    ws *= 20
                dp_msg = int(word_node.get("dp_message", 0))
                status_map = {0: "ok", 16: "missed", 32: "extra", 64: "repeat", 128: "replace"}
                status = status_map.get(dp_msg, "unknown")
                sylls = []
                for syll_node in word_node.iter("syll"):
                    ss = float(syll_node.get("syll_score", 0))
                    if ss < 10:
                        ss *= 20
                    serr = int(syll_node.get("serr_msg", 0)) if syll_node.get("serr_msg") else 0
                    phones = []
                    for ph in syll_node.iter("phone"):
                        ph_dp = int(ph.get("dp_message", 0))
                        perr = int(ph.get("perr_msg", 0)) if ph.get("perr_msg") else 0
                        is_yun = ph.get("is_yun", "0")
                        ph_type = "vowel" if is_yun == "1" else "consonant"
                        phones.append({"content": ph.get("content", ""), "type": ph_type, "error": ph_dp != 0 or perr != 0, "tone": ph.get("mono_tone", "")})
                    sylls.append({"content": syll_node.get("content", ""), "score": round(ss), "error": serr in (1, 2049), "phones": phones})
                words.append({"content": content, "score": round(ws), "status": status, "sylls": sylls})
            result["words"] = words
            err_words = [w for w in words if w["status"] != "ok"]
            if total >= 90: result["comment"] = "非常棒！发音准确，表达流畅。"
            elif total >= 75: result["comment"] = "表现不错，可以注意个别单词的发音和连读。"
            elif total >= 60: result["comment"] = "继续加油，建议多跟读原声材料练习。"
            else: result["comment"] = "需要更多练习，建议从基础发音开始。"
    except Exception as e:
        result["comment"] = f"解析出错: {str(e)[:100]}"
    return result


async def assess(audio_data: bytes, text: str, category: str = "read_sentence", ent: str = "en_vip"):
    """
    调用讯飞ISE评测（SSB+TTP+AUW三步协议）
    """
    pcm_data = _wav_to_pcm(audio_data)  # 直接发WAV数据，ISE自己处理
    pcm_data = pcm_data  # no truncation
    text_b64 = base64.b64encode(("\ufeff" + text).encode("utf-8")).decode()
    
    CHUNK_SIZE = 19000
    chunks = []
    for i in range(0, len(pcm_data), CHUNK_SIZE):
        chunks.append(base64.b64encode(pcm_data[i:i+CHUNK_SIZE]).decode())
    if not chunks:
        chunks = [""]
    
    url = _build_auth_url()
    final_result = None
    
    try:
        async with websockets.connect(url, ping_interval=15, close_timeout=120) as ws:
            # 帧1: SSB（参数，不含文本）
            ssb = {
                "common": {"app_id": "16fe0688"},
                "business": {
                    "sub": "ise", "cmd": "ssb",
                    "ent": ent, "category": category,
                    "aue": "raw", "auf": "audio/L16;rate=16000",
                },
                "data": {"status": 0},
            }
            await ws.send(json.dumps(ssb))
            r = json.loads(await ws.recv())
            if r.get("code") != 0:
                raise Exception(f"SSB fail: {r.get('message','')}")
            
            ttp = {"business": {"sub": "ise", "cmd": "ttp"}, "data": {"status": 0, "data": text_b64}}
            await ws.send(json.dumps(ttp))
            r = json.loads(await ws.recv())
            if r.get("code") != 0:
                raise Exception(f"TTP fail: {r.get('message','')}")
            
            # 帧3+: AUW（音频分帧上传）
            for i, chunk in enumerate(chunks):
                await asyncio.sleep(len(chunk)*3/4/32000)
                if i == 0:
                    auw = {"business": {"sub": "ise", "cmd": "auw", "aus": 1}, "data": {"status": 0, "data": chunk}}
                else:
                    auw = {"business": {"sub": "ise", "cmd": "auw", "aus": 2}, "data": {"status": 1, "data": chunk}}
                await ws.send(json.dumps(auw))
            # 始终发送结束帧
            end = {"business": {"sub": "ise", "cmd": "auw", "aus": 4}, "data": {"status": 2, "data": ""}}
            await ws.send(json.dumps(end))
            
            # 接收结果
            async for msg in ws:
                data = json.loads(msg)
                code = data.get("code", -1)
                if code != 0:
                    raise Exception(f"ISE err code={code} msg={data.get('message','')}")
                raw = data.get("data", {}).get("data", "")
                if raw:
                    xml_str = base64.b64decode(raw).decode("utf-8")
                    print("ISE_XML: " + xml_str, flush=True)
                    final_result = _parse_xml_result(xml_str)
                if data.get("data", {}).get("status", 0) == 2:
                    break
                    
    except asyncio.TimeoutError:
        raise Exception("ISE timeout")
    except websockets.exceptions.ConnectionClosed as e:
        raise Exception(f"ISE closed: {e.code} {e.reason}")
    except Exception as e:
        raise Exception(f"ISE error: {str(e)[:200]}")
    
    if final_result is None:
        raise Exception("no result from ISE")
    return final_result