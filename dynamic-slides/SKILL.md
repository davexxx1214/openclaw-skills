---
name: dynamic-slides
description: 将 PPT 图片通过 Kling AI (fal.ai) 的首尾帧技术转换为动态过渡视频。读取图片序列，生成过渡片段并合成为最终 MP4。
---

# Dynamic Slides 🎬

此 Skill 用于管理和运行 `dynamic-slides` 工具（本目录）。

## 核心流程

1. **接收图片**：用户发送 PPT 导出图片（PNG/JPG）。
2. **准备环境**：将图片放入 `PPT/` 目录，建议命名为 `1.png`, `2.png`...
3. **运行转换**：执行 `python main.py`。
4. **输出结果**：生成分段转场视频与 `final.mp4`。

## 常用命令

- **部署/检查环境**：
  ```bash
  cd dynamic-slides
  python -m pip install -r requirements.txt
  ```

- **运行生成**：
  ```bash
  cd dynamic-slides
  python main.py
  ```

## 变量配置

- `FAL_KEY`: 存储在 `dynamic-slides/.env` 中。

## 目录与脚本说明

- `main.py`：主入口，扫描 `PPT/` → 调用 `kling_api.py` → 合成视频。
- `kling_api.py`：封装 fal.ai Kling API 调用与视频下载。
- `video_composer.py`：FFmpeg 拼接工具与分辨率归一化。
- `config.py`：读取 `.env` 与全局配置（路径、模型、时长、FFmpeg 参数）。
- `prompt.txt`：转场提示词模板，可按需修改。

## 输入/输出约定

- 输入：`PPT/` 中的图片文件（支持 `png/jpg/jpeg/webp`）。
- 输出：`output/YYYYMMDD_HHMMSS/` 目录内的分段视频与 `final.mp4`。

## 注意事项

- **不自动重命名**图片，仅按文件名中的数字排序。
- **不自动清理**输出目录，如需清理请手动删除 `PPT/` 或 `output/`。
- Windows 请确保 `ffmpeg` 在 PATH 中。
