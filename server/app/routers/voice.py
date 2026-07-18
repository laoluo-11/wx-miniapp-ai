from fastapi import APIRouter, Depends, UploadFile, File
from app.utils.auth import current_user
import os, uuid

router = APIRouter(prefix="/api/v1/voice", tags=["Voice"])

@router.post("/assess")
async def assess(audio: UploadFile = File(...), user: dict = Depends(current_user)):
    # TODO: 接入语音评测 AI 服务
    # 当前返回模拟结果
    return {
        "score": 85,
        "comment": "整体表现不错，注意连读与重音位置。",
        "dimensions": [
            {"name": "流利度", "score": 86},
            {"name": "发音", "score": 82},
            {"name": "准确度", "score": 84},
            {"name": "完整度", "score": 88},
        ]
    }

