"""
FFmpeg 视频合成 - 将多个视频片段拼接成完整视频
"""

import subprocess
import shutil
from pathlib import Path
from typing import List

from config import FFMPEG_CODEC, FFMPEG_FPS, FFMPEG_CRF


def check_ffmpeg() -> bool:
    """
    检查 FFmpeg 是否已安装
    
    Returns:
        是否可用
    """
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        print(f"✓ FFmpeg 已找到: {ffmpeg_path}")
        return True
    else:
        print("✗ FFmpeg 未找到！请安装 FFmpeg 并添加到 PATH")
        return False


def get_video_info(video_path: Path) -> dict:
    """
    获取视频信息
    
    Args:
        video_path: 视频路径
        
    Returns:
        视频信息字典
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration,r_frame_rate",
        "-of", "csv=p=0",
        str(video_path)
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        parts = result.stdout.strip().split(",")
        if len(parts) >= 3:
            return {
                "width": int(parts[0]),
                "height": int(parts[1]),
                "duration": float(parts[2]) if parts[2] else 0,
            }
    except Exception as e:
        print(f"警告: 无法获取视频信息 {video_path}: {e}")
    
    return {}


def concatenate_videos(
    video_paths: List[Path],
    output_path: Path,
    normalize_resolution: bool = True,
) -> bool:
    """
    使用 FFmpeg 拼接多个视频
    
    Args:
        video_paths: 视频路径列表（按顺序）
        output_path: 输出视频路径
        normalize_resolution: 是否统一分辨率
        
    Returns:
        是否成功
    """
    if not video_paths:
        print("错误: 没有视频文件可拼接")
        return False
    
    if not check_ffmpeg():
        return False
    
    print(f"\n{'='*50}")
    print("🔗 开始拼接视频")
    print(f"{'='*50}")
    print(f"视频数量: {len(video_paths)}")
    
    # 确保输出目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 创建临时文件列表
    filelist_path = output_path.parent / "filelist.txt"
    
    try:
        # 写入文件列表
        with open(filelist_path, "w", encoding="utf-8") as f:
            for video_path in video_paths:
                # 使用绝对路径，并转义特殊字符
                abs_path = str(video_path.absolute()).replace("\\", "/")
                f.write(f"file '{abs_path}'\n")
                print(f"  + {video_path.name}")
        
        # 构建 FFmpeg 命令
        if normalize_resolution:
            # 使用 filter_complex 统一分辨率和帧率
            cmd = build_normalized_concat_command(video_paths, output_path)
        else:
            # 简单拼接（要求所有视频格式一致）
            cmd = [
                "ffmpeg",
                "-y",  # 覆盖输出文件
                "-f", "concat",
                "-safe", "0",
                "-i", str(filelist_path),
                "-c", "copy",
                str(output_path)
            ]
        
        print(f"\n⚙️  执行 FFmpeg 命令...")
        
        # 执行命令
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
        
        if result.returncode == 0:
            print(f"\n✓ 视频拼接成功!")
            print(f"  输出: {output_path}")
            
            # 显示输出文件信息
            if output_path.exists():
                size_mb = output_path.stat().st_size / (1024 * 1024)
                print(f"  大小: {size_mb:.2f} MB")
            
            return True
        else:
            print(f"\n✗ 视频拼接失败!")
            print(f"错误信息: {result.stderr}")
            return False
            
    finally:
        # 清理临时文件
        if filelist_path.exists():
            filelist_path.unlink()


def build_normalized_concat_command(
    video_paths: List[Path],
    output_path: Path,
    target_width: int = 1920,
    target_height: int = 1080,
) -> List[str]:
    """
    构建统一分辨率的拼接命令
    
    Args:
        video_paths: 视频路径列表
        output_path: 输出路径
        target_width: 目标宽度
        target_height: 目标高度
        
    Returns:
        FFmpeg 命令列表
    """
    cmd = ["ffmpeg", "-y"]
    
    # 添加所有输入文件
    for video_path in video_paths:
        cmd.extend(["-i", str(video_path)])
    
    # 构建 filter_complex
    n = len(video_paths)
    filter_parts = []
    
    # 为每个视频统一分辨率和帧率
    for i in range(n):
        filter_parts.append(
            f"[{i}:v]scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
            f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2,"
            f"fps={FFMPEG_FPS},format=yuv420p[v{i}]"
        )
    
    # 拼接所有视频
    concat_inputs = "".join(f"[v{i}]" for i in range(n))
    filter_parts.append(f"{concat_inputs}concat=n={n}:v=1:a=0[outv]")
    
    filter_complex = ";".join(filter_parts)
    
    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-c:v", FFMPEG_CODEC,
        "-crf", str(FFMPEG_CRF),
        "-preset", "medium",
        str(output_path)
    ])
    
    return cmd


def create_video_from_image(
    image_path: Path,
    output_path: Path,
    duration: float = 2.0,
) -> bool:
    """
    从静态图片创建视频（用于首页和尾页停留）
    
    Args:
        image_path: 图片路径
        output_path: 输出视频路径
        duration: 视频时长（秒）
        
    Returns:
        是否成功
    """
    if not check_ffmpeg():
        return False
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        "ffmpeg",
        "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-c:v", FFMPEG_CODEC,
        "-t", str(duration),
        "-pix_fmt", "yuv420p",
        "-vf", f"fps={FFMPEG_FPS},scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        "-crf", str(FFMPEG_CRF),
        str(output_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0
