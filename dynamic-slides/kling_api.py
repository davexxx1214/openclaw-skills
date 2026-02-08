"""
Kling API 封装 - 调用 fal.ai 平台的 Kling 2.6 首尾帧视频生成
"""

import os
import io
import base64
import httpx
from pathlib import Path
from typing import Optional, Callable
import mimetypes
from PIL import Image

# 先加载环境变量（强制覆盖，防止缓存问题）
from dotenv import load_dotenv
load_dotenv(override=True)

# 确保 FAL_KEY 环境变量已设置
FAL_KEY = os.environ.get("FAL_KEY")
if not FAL_KEY:
    raise ValueError("FAL_KEY 环境变量未设置！请检查 .env 文件")

import fal_client

from config import (
    KLING_MODEL_ID,
    VIDEO_DURATION,
    GENERATE_AUDIO,
    NEGATIVE_PROMPT,
    PROMPT_FILE,
)


def get_fal_client():
    """获取 fal 客户端实例（使用 SyncClient 并传入 key）"""
    return fal_client.SyncClient(key=FAL_KEY)


def upload_image_to_fal(image_path: Path) -> str:
    """
    上传本地图片到 fal.ai 并返回 URL
    
    Args:
        image_path: 本地图片路径
        
    Returns:
        图片的 URL
    """
    # 使用 SyncClient 上传文件
    client = get_fal_client()
    url = client.upload_file(str(image_path))
    
    size_mb = image_path.stat().st_size / (1024 * 1024)
    print(f"  ✓ 上传成功: {image_path.name} ({size_mb:.2f} MB)")
    
    return url


def image_to_data_uri(image_path: Path, max_size_mb: float = 1.5, max_dimension: int = 1920) -> str:
    """
    将本地图片压缩并转换为 Base64 Data URI（备用方案）
    
    Args:
        image_path: 本地图片路径
        max_size_mb: 最大文件大小（MB）
        max_dimension: 最大边长（像素）
        
    Returns:
        Base64 Data URI 格式的字符串
    """
    # 打开图片
    img = Image.open(image_path)
    original_size = image_path.stat().st_size / (1024 * 1024)
    
    # 如果图片太大，先缩放
    width, height = img.size
    if max(width, height) > max_dimension:
        ratio = max_dimension / max(width, height)
        new_size = (int(width * ratio), int(height * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
        print(f"  → 缩放: {width}x{height} -> {new_size[0]}x{new_size[1]}")
    
    # 转换为 RGB（如果是 RGBA）
    if img.mode == 'RGBA':
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background
    elif img.mode != 'RGB':
        img = img.convert('RGB')
    
    # 压缩为 JPEG 并调整质量直到满足大小要求
    quality = 85
    while quality >= 30:
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=quality, optimize=True)
        image_data = buffer.getvalue()
        size_mb = len(image_data) / (1024 * 1024)
        
        if size_mb <= max_size_mb:
            break
        quality -= 10
    
    # 编码为 Base64
    base64_data = base64.b64encode(image_data).decode('utf-8')
    data_uri = f"data:image/jpeg;base64,{base64_data}"
    
    print(f"  ✓ 已编码: {image_path.name} ({original_size:.2f} MB -> {size_mb:.2f} MB, Q={quality})")
    
    return data_uri


def generate_transition_video(
    start_image_path: Path,
    end_image_path: Path,
    prompt: str,
    output_path: Path,
    on_progress: Optional[Callable] = None,
) -> dict:
    """
    使用 Kling 2.6 API 生成首尾帧转场视频
    
    Args:
        start_image_path: 起始帧图片路径
        end_image_path: 结束帧图片路径
        prompt: 转场描述提示词
        output_path: 输出视频路径
        on_progress: 进度回调函数
        
    Returns:
        API 响应结果
    """
    print(f"\n{'='*50}")
    print(f"生成转场视频: {start_image_path.name} → {end_image_path.name}")
    print(f"{'='*50}")
    
    # 获取 fal 客户端
    client = get_fal_client()
    
    # 上传图片到 fal.ai
    print("\n📤 上传图片...")
    try:
        start_image_url = client.upload_file(str(start_image_path))
        print(f"  ✓ 上传成功: {start_image_path.name}")
        
        end_image_url = client.upload_file(str(end_image_path))
        print(f"  ✓ 上传成功: {end_image_path.name}")
    except Exception as upload_error:
        print(f"  ⚠️ 上传失败: {upload_error}")
        print("  📷 尝试使用 Base64 编码...")
        start_image_url = image_to_data_uri(start_image_path)
        end_image_url = image_to_data_uri(end_image_path)
    
    # 构建请求参数
    arguments = {
        "prompt": prompt,
        "start_image_url": start_image_url,
        "end_image_url": end_image_url,
        "duration": VIDEO_DURATION,
        "generate_audio": GENERATE_AUDIO,
        "negative_prompt": NEGATIVE_PROMPT,
    }
    
    print(f"\n🎬 调用 Kling API 生成视频...")
    print(f"   模型: {KLING_MODEL_ID}")
    print(f"   时长: {VIDEO_DURATION}秒")
    print(f"   音频: {'开启' if GENERATE_AUDIO else '关闭'}")
    
    # 调用 API（使用 SyncClient 的 subscribe 方法）
    result = client.subscribe(
        KLING_MODEL_ID,
        arguments=arguments,
        with_logs=True,
    )
    
    print(f"\n📋 API 响应: {result}")
    
    # 下载视频
    if result and "video" in result:
        video_url = result["video"]["url"]
        print(f"\n📥 下载视频: {video_url[:80]}...")
        
        download_video(video_url, output_path)
        print(f"   ✓ 保存到: {output_path}")
        
        return result
    else:
        raise Exception(f"API 返回结果异常: {result}")


def download_video(url: str, output_path: Path):
    """
    下载视频文件
    
    Args:
        url: 视频 URL
        output_path: 保存路径
    """
    # 确保输出目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 下载视频
    with httpx.Client(timeout=300) as client:
        response = client.get(url)
        response.raise_for_status()
        
        with open(output_path, "wb") as f:
            f.write(response.content)


def get_transition_prompt() -> str:
    """
    从 prompt.txt 读取转场提示词
    
    Returns:
        提示词内容
    """
    if PROMPT_FILE.exists():
        prompt = PROMPT_FILE.read_text(encoding="utf-8").strip()
        print(f"✓ 已加载提示词文件: {PROMPT_FILE.name}")
        return prompt
    else:
        print(f"⚠️ 提示词文件不存在: {PROMPT_FILE}，使用默认提示词")
        return (
            "Smooth cinematic transition between two frames. "
            "The scene transforms fluidly with natural camera movement. "
            "Maintain visual continuity while elements morph and blend seamlessly. "
            "Professional broadcast quality with smooth motion blur."
        )
