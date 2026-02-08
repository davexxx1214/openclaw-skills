"""
配置文件 - 读取环境变量和全局配置
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# ===== API 配置 =====
FAL_KEY = os.getenv("FAL_KEY")

if not FAL_KEY:
    raise ValueError(
        "未找到 FAL_KEY 环境变量！\n"
        "请复制 .env.example 为 .env 并填入你的 API Key:\n"
        "  cp .env.example .env\n"
        "  然后编辑 .env 文件"
    )

# ===== 路径配置 =====
BASE_DIR = Path(__file__).parent
PPT_DIR = BASE_DIR / "PPT"
OUTPUT_DIR = BASE_DIR / "output"
PROMPT_FILE = BASE_DIR / "prompt.txt"

# ===== Kling API 配置 =====
KLING_MODEL_ID = "fal-ai/kling-video/v2.6/pro/image-to-video"
VIDEO_DURATION = "5"  # 视频时长：5秒或10秒
GENERATE_AUDIO = False  # 不生成音频
NEGATIVE_PROMPT = "blur, distort, and low quality"

# ===== 支持的图片格式 =====
SUPPORTED_IMAGE_FORMATS = (".png", ".jpg", ".jpeg", ".webp")

# ===== FFmpeg 配置 =====
FFMPEG_CODEC = "libx264"
FFMPEG_FPS = 30
FFMPEG_CRF = 23  # 质量控制，越小质量越高

# ===== 转场提示词模板 =====
TRANSITION_PROMPT_TEMPLATE = """你是一位顶尖的创意视频导演和VFX（视觉特效）概念艺术家。你的任务是为AI视频生成模型设计一个从【起始帧】到【结束帧】的转场过程。

你的核心目标是：构思并用一段话清晰、具体地描述这个动态视觉变化。

在构思时，请遵循以下创作框架：

第一步：分析差异 快速判断【起始帧】和【结束帧】的差异程度。

A类 - 关联性强： 主体或场景基本一致，只是状态、风格或环境发生改变（例如，同一个人换了衣服，同一个场景从白天到黑夜）。

B类 - 差异巨大： 主体和场景完全不同（例如，一只猫在客厅 → 一艘飞船在太空）。

第二步：选择转场策略

如果属于 A类，优先采用**"原地演变"的策略。让变化直接发生在主体和环境上，尽量不使用或只使用微弱的摄像机移动。

如果属于 B类，采用"运镜驱动转场"**的策略。必须使用一种明确的摄像机移动（如推、拉、摇、移、旋转）来引导过渡，让镜头运动成为连接两个不相干画面的桥梁。

第三步：构思具体变化（从以下工具箱中选择组合）

主体变化： 主体如何改变？（形态变化、材质替换、服装更替、分解重组、消失或出现）。

环境变化： 背景如何改变？（时间流逝、季节更替、空间切换、从现实变为幻想）。

风格/特效变化： 用什么视觉风格或特效来包装这个过程？（例如，画面逐渐像素化后重组、被火焰/水流吞噬后显现、转变为水彩/油画风格、出现光效粒子）。

输出规则：

将你的最终构思整合为一个连贯的段落。

描述要具体、直接，充满画面感。专注于"我们看到了什么"，而不是"我们感觉到了什么"。

严格遵守你在第二步中选择的摄像机移动策略。

避免使用模糊的比喻和过于文学化的修辞。"""
