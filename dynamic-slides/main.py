"""
Dynamic-Slides 主入口脚本
将 PPT 图片转换为流畅的动态视频
"""

import re
import sys
import io
from pathlib import Path
from datetime import datetime
from typing import List, Tuple

# 修复 Windows 终端中文乱码问题，并启用行缓冲实时输出
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)

from config import PPT_DIR, OUTPUT_DIR, SUPPORTED_IMAGE_FORMATS
from kling_api import generate_transition_video, get_transition_prompt
from video_composer import concatenate_videos, check_ffmpeg


def get_sorted_images(ppt_dir: Path) -> List[Path]:
    """
    获取 PPT 文件夹中的图片，按数字命名排序
    
    支持的命名格式:
    - 1.png, 2.png, 3.png, ...
    - 01.png, 02.png, 03.png, ...
    - slide_1.png, slide_2.png, ...
    
    Args:
        ppt_dir: PPT 图片文件夹路径
        
    Returns:
        排序后的图片路径列表
    """
    if not ppt_dir.exists():
        raise FileNotFoundError(f"PPT 文件夹不存在: {ppt_dir}")
    
    # 获取所有支持格式的图片（使用 set 去重，因为 Windows 不区分大小写）
    images_set = set()
    for ext in SUPPORTED_IMAGE_FORMATS:
        images_set.update(ppt_dir.glob(f"*{ext}"))
        images_set.update(ppt_dir.glob(f"*{ext.upper()}"))
    
    # 过滤掉 .gitkeep 等非图片文件
    images = [img for img in images_set if img.suffix.lower() in SUPPORTED_IMAGE_FORMATS]
    
    if not images:
        raise FileNotFoundError(
            f"PPT 文件夹中没有找到图片!\n"
            f"支持的格式: {', '.join(SUPPORTED_IMAGE_FORMATS)}\n"
            f"请将图片放入: {ppt_dir}"
        )
    
    # 按数字排序
    def extract_number(path: Path) -> int:
        """从文件名中提取数字用于排序"""
        # 匹配文件名中的数字
        numbers = re.findall(r'\d+', path.stem)
        if numbers:
            return int(numbers[0])
        return 0
    
    images.sort(key=extract_number)
    
    return images


def generate_image_pairs(images: List[Path]) -> List[Tuple[Path, Path, int]]:
    """
    生成首尾帧图片对
    
    Args:
        images: 排序后的图片列表
        
    Returns:
        (起始帧, 结束帧, 序号) 的列表
    """
    pairs = []
    for i in range(len(images) - 1):
        pairs.append((images[i], images[i + 1], i + 1))
    return pairs


def main():
    """主函数"""
    print("""
╔══════════════════════════════════════════════════════════╗
║                    Dynamic-Slides                        ║
║         将静态 PPT 图片转换为流畅动态视频                ║
╚══════════════════════════════════════════════════════════╝
    """)
    
    # 检查 FFmpeg
    if not check_ffmpeg():
        print("\n请先安装 FFmpeg!")
        print("下载地址: https://ffmpeg.org/download.html")
        sys.exit(1)
    
    # 获取排序后的图片
    print(f"\n📁 扫描 PPT 文件夹: {PPT_DIR}")
    
    try:
        images = get_sorted_images(PPT_DIR)
    except FileNotFoundError as e:
        print(f"\n❌ 错误: {e}")
        print("\n请按以下步骤操作:")
        print(f"  1. 创建 PPT 文件夹: {PPT_DIR}")
        print("  2. 将 PPT 导出的图片放入文件夹")
        print("  3. 图片命名格式: 1.png, 2.png, 3.png, ...")
        sys.exit(1)
    
    print(f"✓ 找到 {len(images)} 张图片:")
    for img in images:
        print(f"   - {img.name}")
    
    # 生成图片对
    pairs = generate_image_pairs(images)
    print(f"\n🎬 需要生成 {len(pairs)} 个转场视频")
    
    if not pairs:
        print("❌ 至少需要 2 张图片才能生成转场视频!")
        sys.exit(1)
    
    # 创建输出目录（使用时间戳）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = OUTPUT_DIR / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n📂 输出目录: {output_dir}")
    
    # 获取转场提示词（从 prompt.txt 读取）
    prompt = get_transition_prompt()
    print(f"\n📝 转场提示词: {prompt[:80]}...")
    
    # 生成所有转场视频
    video_paths = []
    failed = []
    
    for start_img, end_img, idx in pairs:
        output_video = output_dir / f"{idx}.mp4"
        
        try:
            generate_transition_video(
                start_image_path=start_img,
                end_image_path=end_img,
                prompt=prompt,
                output_path=output_video,
            )
            video_paths.append(output_video)
            print(f"\n✓ 视频 {idx}/{len(pairs)} 生成成功!")
            
        except Exception as e:
            print(f"\n❌ 视频 {idx}/{len(pairs)} 生成失败: {e}")
            failed.append((idx, str(e)))
    
    # 检查是否有失败的视频
    if failed:
        print(f"\n⚠️  警告: {len(failed)} 个视频生成失败:")
        for idx, error in failed:
            print(f"   - 视频 {idx}: {error}")
    
    # 拼接视频
    if video_paths:
        print(f"\n{'='*50}")
        print("开始拼接最终视频...")
        print(f"{'='*50}")
        
        final_video = output_dir / "final.mp4"
        
        success = concatenate_videos(
            video_paths=video_paths,
            output_path=final_video,
            normalize_resolution=True,
        )
        
        if success:
            print(f"""
╔══════════════════════════════════════════════════════════╗
║                      🎉 完成!                            ║
╠══════════════════════════════════════════════════════════╣
║  转场视频: {len(video_paths)} 个
║  最终视频: {final_video}
╚══════════════════════════════════════════════════════════╝
            """)
        else:
            print("\n❌ 视频拼接失败!")
    else:
        print("\n❌ 没有成功生成任何视频，无法拼接!")
        sys.exit(1)


if __name__ == "__main__":
    main()
