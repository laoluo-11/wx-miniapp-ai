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
import websockets
from app.config import XF_API_KEY, XF_API_SECRET

ISE_HOST = "ise-api.xfyun.cn"
ISE_PATH = "/v2/open-ise"
ISE_URL = f"wss://{ISE_HOST}{ISE_PATH}"

def _build_auth_url():
    """生成带签名的 WebSocket URL（参数需URL编码）"""
    import datetime
    from urllib.parse import quote
    now = datetime.datetime.utcnow()
    date = now.strftime("%a, %d %b %Y %H:%M:%S GMT")
    
    signature_origin = f"host: {ISE_HOST}\ndate: {date}\nGET {ISE_PATH} HTTP/1.1"
    signature = base64.b64encode(
        hmac.new(XF_API_SECRET.encode(), signature_origin.encode(), hashlib.sha256).digest()
    ).decode()
    
    auth_origin = f'api_key="{XF_API_KEY}",algorithm="hmac-sha256",headers="host date request-line",signature="{signature}"'
    authorization = base64.b64encode(auth_origin.encode()).decode()
    
    # URL编码参数（base64含+/=，日期含空格逗号）
    return (
        f"{ISE_URL}"
        f"?authorization={quote(authorization)}"
        f"&date={quote(date)}"
        f"&host={quote(ISE_HOST)}"
    )


def _wav_to_pcm(wav_bytes):
    """去除WAV头（44字节），提取原始PCM数据"""
    if len(wav_bytes) < 44:
        return wav_bytes
    # 检查WAV头
    if wav_bytes[:4] != b'RIFF' or wav_bytes[8:12] != b'WAVE':
        # 不是WAV，直接返回
        return wav_bytes
    # 跳过WAV头，找到data chunk
    offset = 12
    while offset < len(wav_bytes) - 8:
        chunk_id = wav_bytes[offset:offset+4]
        chunk_size = struct.unpack('<I', wav_bytes[offset+4:offset+8])[0]
        if chunk_id == b'data':
            return wav_bytes[offset+8:offset+8+chunk_size]
        offset += 8 + chunk_size
    # 兜底：跳过44字节标准头
    return wav_bytes[44:]


def _parse_xml_result(xml_str):
    """解析讯飞返回的XML评测结果，提取句子/单词/音节/音素各级评分"""
    import xml.etree.ElementTree as ET
    result = {"score": 0, "comment": "", "dimensions": [], "words": []}
    
    try:
        root = ET.fromstring(xml_str)
        
        # 查找 read_sentence 或 read_chapter 节点
        read_node = root.find('.//read_sentence') or root.find('.//read_chapter')
        if read_node is not None:
            total = float(read_node.get('total_score', 0))
            accuracy = float(read_node.get('accuracy_score', 0))
            fluency = float(read_node.get('fluency_score', 0))
            integrity = float(read_node.get('integrity_score', 0))
            standard = float(read_node.get('standard_score', 0))
            
            result["score"] = round(total)
            result["dimensions"] = [
                {"name": "准确度", "score": round(accuracy)},
                {"name": "流利度", "score": round(fluency)},
                {"name": "完整度", "score": round(integrity)},
                {"name": "标准度", "score": round(standard)},
            ]
            
            # 提取单词级别评分
            words = []
            for word_node in read_node.iter('word'):
                content = word_node.get('content', '')
                word_score = float(word_node.get('total_score', 0))
                dp_msg = int(word_node.get('dp_message', 0))
                
                # dp_message: 0=正常, 16=漏读, 32=增读, 64=回读, 128=替换
                status_map = {0: "ok", 16: "missed", 32: "extra", 64: "repeat", 128: "replace"}
                status = status_map.get(dp_msg, "unknown")
                
                # 提取音节
                sylls = []
                for syll_node in word_node.iter('syll'):
                    syll_content = syll_node.get('content', '')
                    syll_score = float(syll_node.get('syll_score', 0))
                    serr = int(syll_node.get('serr_msg', 0)) if syll_node.get('serr_msg') else 0
                    syll_error = serr in (1, 2049)
                    
                    # 提取音素
                    phones = []
                    for ph in syll_node.iter('phone'):
                        ph_content = ph.get('content', '')
                        ph_dp = int(ph.get('dp_message', 0))
                        is_yun = ph.get('is_yun', '0')
                        perr = int(ph.get('perr_msg', 0)) if ph.get('perr_msg') else 0
                        tone = ph.get('mono_tone', '')
                        
                        ph_type = "vowel" if is_yun == "1" else "consonant"
                        ph_error = ph_dp != 0 or perr != 0
                        
                        phones.append({
                            "content": ph_content,
                            "type": ph_type,
                            "error": ph_error,
                            "tone": tone,
                        })
                    
                    sylls.append({
                        "content": syll_content,
                        "score": round(syll_score),
                        "error": syll_error,
                        "phones": phones,
                    })
                
                words.append({
                    "content": content,
                    "score": round(word_score),
                    "status": status,
                    "sylls": sylls,
                })
            
            result["words"] = words
            
            # 生成评语 + 错误单词统计
            error_words = [w for w in words if w["status"] != "ok"]
            if total >= 90:
                result["comment"] = "非常棒！发音准确，表达流畅。"
            elif total >= 75:
                detail = ""
                if error_words:
                    detail = f"其中{len(error_words)}个单词需要改进。"
                result["comment"] = f"表现不错，可以注意个别单词的发音和连读。{detail}"
            elif total >= 60:
                detail = ""
                if error_words:
                    bad_words = ", ".join(w["content"] for w in error_words[:5])
                    detail = f"重点练习: {bad_words}。"
                result["comment"] = f"继续加油，建议多跟读原声材料。{detail}"
            else:
                result["comment"] = "需要更多练习，建议从基础发音开始，逐步提高。"
        
        elif root.find('.//read_word') is not None:
            word_node = root.find('.//read_word')
            total = float(word_node.get('total_score', 0))
            result["score"] = round(total)
            result["dimensions"] = [{"name": "总分", "score": round(total)}]
            result["comment"] = "评测完成。"
            
    except Exception as e:
        result["comment"] = f"解析结果出错: {str(e)[:100]}"
    
    return result


async def assess(audio_data: bytes, text: str, category: str = "read_sentence", ent: str = "en_vip"):
    """
    调用讯飞ISE评测（流式分帧发送音频）
    """
    pcm_data = _wav_to_pcm(audio_data)
    # 文本加 UTF-8 BOM 头再 base64
    text_b64 = base64.b64encode(('\ufeff' + text).encode("utf-8")).decode()
    
    # 分帧音频
    CHUNK_SIZE = 640
    chunks = []
    for i in range(0, len(pcm_data), CHUNK_SIZE):
        chunk = pcm_data[i:i+CHUNK_SIZE]
        chunks.append(base64.b64encode(chunk).decode())
    if not chunks: chunks = [""]
    
    url = _build_auth_url()
    final_result = None
    
    try:
        async with websockets.connect(url, ping_interval=10, close_timeout=10) as ws:
            # 帧1: ssb (参数上传)
            ssb_frame = {
                "common": {"app_id": "16fe0688"},
                "business": {
                    "sub": "ise",
                    "cmd": "ssb",
                    "ent": ent,
                    "category": category,
                    "aue": "raw",
                    "auf": "audio/L16;rate=16000",
                    "text": text_b64,
                    "rst": "utf8",
                    "tte": "utf-8",
                },
                "data": {"status": 0, "data": ""},
            }
            await ws.send(json.dumps(ssb_frame))
            
            # 帧2+: auw (音频上传)
            for i, chunk in enumerate(chunks):
                if i == 0:
                    aus = 1; st = 0
                elif i == len(chunks) - 1:
                    aus = 4; st = 2
                else:
                    aus = 2; st = 1
                
                audio_frame = {
                    "business": {"sub": "ise", "cmd": "auw", "aus": aus},
                    "data": {"status": st, "data": chunk},
                }
                await ws.send(json.dumps(audio_frame))
                await asyncio.sleep(0.03)
            
            await asyncio.sleep(0.5)
            # 等待结果
            async for msg in ws:
                data = json.loads(msg)
                code = data.get("code", -1)
                if code != 0:
                    raise Exception(f"ISE err code={code} msg='{data.get('message','')}'")
                
                raw = data.get("data", {}).get("data", "")
                if raw:
                    try:
                        xml_str = base64.b64decode(raw).decode("utf-8")
                        final_result = _parse_xml_result(xml_str)
                    except Exception as e:
                        raise Exception(f"parse fail: {str(e)[:100]}")
                
                if data.get("data", {}).get("status", 0) == 2:
                    break
                    
    except asyncio.TimeoutError:
        raise Exception("ISE timeout")
    except websockets.exceptions.ConnectionClosed as e:
        raise Exception(f"ISE closed: {e.code} {e.reason}")
    except Exception as e:
        raise Exception(f"ISE error: {str(e)[:200]}")
    
    if final_result is None:
        raise Exception("no result")
    return final_result