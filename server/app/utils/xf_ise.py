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
    """生成带签名的 WebSocket URL"""
    import datetime
    now = datetime.datetime.utcnow()
    date = now.strftime("%a, %d %b %Y %H:%M:%S GMT")
    
    signature_origin = f"host: {ISE_HOST}\ndate: {date}\nGET {ISE_PATH} HTTP/1.1"
    signature = base64.b64encode(
        hmac.new(XF_API_SECRET.encode(), signature_origin.encode(), hashlib.sha256).digest()
    ).decode()
    
    authorization = base64.b64encode(
        f'api_key="{XF_API_KEY}",algorithm="hmac-sha256",headers="host date request-line",signature="{signature}"'.encode()
    ).decode()
    
    return f"{ISE_URL}?authorization={authorization}&date={date}&host={ISE_HOST}"


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
    """解析讯飞返回的XML评测结果，提取关键分数"""
    import xml.etree.ElementTree as ET
    result = {"score": 0, "comment": "", "dimensions": []}
    
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
            
            # 生成评语
            if total >= 90:
                result["comment"] = "非常棒！发音准确，表达流畅。"
            elif total >= 75:
                result["comment"] = "表现不错，可以注意个别单词的发音和连读。"
            elif total >= 60:
                result["comment"] = "继续加油，建议多跟读原声材料练习发音。"
            else:
                result["comment"] = "需要更多练习，建议从基础发音开始，逐步提高。"
        else:
            # 尝试 word 题型
            word_node = root.find('.//read_word')
            if word_node is not None:
                total = float(word_node.get('total_score', 0))
                result["score"] = round(total)
                result["dimensions"] = [{"name": "总分", "score": round(total)}]
                result["comment"] = "评测完成。"
            
    except Exception as e:
        result["comment"] = f"解析结果出错: {str(e)[:100]}"
    
    return result


async def assess(audio_data: bytes, text: str, category: str = "read_sentence", ent: str = "en_vip"):
    """
    调用讯飞ISE评测
    
    Args:
        audio_data: 音频数据（WAV格式，16kHz 16bit 单声道）
        text: 评测参考文本
        category: 题型，read_sentence/read_chapter/read_word
        ent: 引擎，en_vip=英文，cn_vip=中文
    
    Returns:
        {"score": int, "comment": str, "dimensions": [...]}
    """
    # 去除WAV头，提取PCM
    pcm_data = _wav_to_pcm(audio_data)
    # Base64编码
    audio_b64 = base64.b64encode(pcm_data).decode()
    text_b64 = base64.b64encode(text.encode("utf-8")).decode()
    
    url = _build_auth_url()
    
    # 首帧参数
    first_frame = {
        "common": {"app_id": XF_API_KEY},
        "business": {
            "cmd": "auw",
            "aus": 1,
            "ent": ent,
            "category": category,
            "aue": "raw",
            "auf": "audio/L16;rate=16000",
            "rst": "utf8",
            "tte": "utf-8",
            "text": text_b64,
        },
        "data": {
            "status": 0,
            "data": audio_b64,
        },
    }
    
    # 中间帧（同一音频作为完整数据，status=1）
    mid_frame = {
        "business": {"cmd": "auw", "aus": 1},
        "data": {"status": 1, "data": audio_b64},
    }
    
    # 末帧
    end_frame = {
        "business": {"cmd": "auw", "aus": 1},
        "data": {"status": 2, "data": ""},
    }
    
    final_result = None
    
    try:
        async with websockets.connect(url, ping_interval=10, close_timeout=5) as ws:
            # 发送首帧
            await ws.send(json.dumps(first_frame))
            
            # 短暂等待后发送末帧（ISE需要一点处理时间）
            await asyncio.sleep(0.1)
            
            # 发送末帧
            await ws.send(json.dumps(end_frame))
            
            # 接收结果
            async for msg in ws:
                data = json.loads(msg)
                code = data.get("code", -1)
                if code != 0:
                    raise Exception(f"讯飞返回错误: code={code}, message={data.get('message', '')}")
                
                # 解析返回数据
                raw = data.get("data", {}).get("data", "")
                if raw:
                    try:
                        xml_bytes = base64.b64decode(raw)
                        xml_str = xml_bytes.decode("utf-8")
                        final_result = _parse_xml_result(xml_str)
                    except Exception as e:
                        raise Exception(f"解析评测结果失败: {str(e)[:100]}")
                
                status = data.get("data", {}).get("status", 0)
                if status == 2:
                    break
                    
    except asyncio.TimeoutError:
        raise Exception("讯飞评测超时")
    except Exception as e:
        raise Exception(f"讯飞评测异常: {str(e)[:200]}")
    
    if final_result is None:
        raise Exception("未收到评测结果")
    
    return final_result
