# Dynamic-Slides 🎬

基于 AI 首尾帧技术，将静态 PPT 图片转换为流畅动态视频的 Python 工具。

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Kling](https://img.shields.io/badge/Kling-2.6-green.svg)](https://fal.ai/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ✨ 功能特性

- 🖼️ **智能图片读取** - 自动扫描 PPT 文件夹，按数字命名顺序排列
- 🎥 **AI 首尾帧生成** - 调用 fal 平台 Kling 2.6 API，生成丝滑过渡动画
- 🔗 **自动视频拼接** - 使用 FFmpeg 无缝合成完整演示视频
- ⚡ **简单易用** - 一键运行，自动完成全部流程

---

## 🎯 工作原理

```
PPT/
├── 1.png  ─┬─→ Kling API ─→ 1.mp4 (1→2 过渡)
├── 2.png  ─┴─┬─→ Kling API ─→ 2.mp4 (2→3 过渡)
├── 3.png  ───┴─┬─→ Kling API ─→ 3.mp4 (3→4 过渡)
├── ...         │
└── n.png  ─────┘

最终输出: 1.mp4 + 2.mp4 + ... + (n-1).mp4 → output.mp4
```

### 视频生成逻辑

| 序号 | 首帧 | 尾帧 | 输出 |
|------|------|------|------|
| 1 | 1.png | 2.png | 1.mp4 |
| 2 | 2.png | 3.png | 2.mp4 |
| 3 | 3.png | 4.png | 3.mp4 |
| ... | ... | ... | ... |
| n-1 | (n-1).png | n.png | (n-1).mp4 |

---

## 🚀 快速开始

### 环境要求

- Python 3.8+
- FFmpeg（Windows 系统需添加到 PATH）
- fal.ai 账号和 API Key

### 安装步骤

1. **克隆项目**

```bash
git clone https://github.com/your-username/Dynamic-Slides.git
cd Dynamic-Slides
```

2. **安装依赖**

```bash
pip install -r requirements.txt
```

3. **配置环境变量**

创建 `.env` 文件并填入你的 fal.ai API Key：

```bash
# Windows PowerShell
echo "FAL_KEY=your_fal_api_key_here" > .env

# 或手动创建 .env 文件，内容如下：
```

```env
FAL_KEY=your_fal_api_key_here
```

4. **准备 PPT 图片**

将你的 PPT 页面导出为图片，放入 `PPT/` 文件夹：

```
PPT/
├── 1.png
├── 2.png
├── 3.png
└── ...
```

### 运行

```bash
python main.py
```

---

## 📁 项目结构

```
Dynamic-Slides/
│
├── .env                      # 环境变量（需手动创建，不提交到 Git）
├── .gitignore                # Git 忽略规则
├── requirements.txt          # Python 依赖
├── README.md                 # 项目说明
│
├── main.py                   # 主入口脚本
├── config.py                 # 配置文件（读取环境变量）
├── kling_api.py              # Kling API 封装（fal 平台）
├── video_composer.py         # FFmpeg 视频合成
│
├── PPT/                      # PPT 图片输入文件夹
│   ├── 1.png
│   ├── 2.png
│   └── ...
│
└── output/                   # 输出文件夹（自动创建）
    └── YYYYMMDD_HHMMSS/      # 按时间戳创建的子文件夹
        ├── 1.mp4             # 过渡视频片段
        ├── 2.mp4
        ├── ...
        └── final.mp4         # 最终合成视频
```

---

## 🔧 配置选项

### Kling 2.6 API 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| model | kling-video/v2.6/pro/image-to-video | 使用的模型版本 |
| duration | 5s | 每段过渡视频时长 |
| aspect_ratio | 16:9 | 视频宽高比 |

### FFmpeg 合成参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| codec | libx264 | 视频编码器 |
| fps | 30 | 帧率 |
| resolution | 1920x1080 | 输出分辨率 |

---

## 📋 使用建议

### 图片命名规范

- ✅ 推荐：`1.png`, `2.png`, `3.png`, ...
- ✅ 支持：`01.png`, `02.png`, ... (会自动按数字排序)
- ❌ 避免：`slide_a.png`, `intro.png` (非数字命名)

### PPT 导出建议

| 分辨率 | 尺寸 | 推荐场景 |
|--------|------|----------|
| 1080p | 1920x1080 | 日常演示、在线分享 ✅ |
| 2K | 2560x1440 | 高清展示 |
| 4K | 3840x2160 | 大屏展示、打印 |

### 页数与时长估算

| PPT 页数 | 过渡视频数 | 预计总时长 (5s/段) |
|----------|------------|---------------------|
| 5 页 | 4 段 | ~20 秒 |
| 10 页 | 9 段 | ~45 秒 |
| 20 页 | 19 段 | ~95 秒 |

---

## ❓ 常见问题

### Q: 如何获取 fal.ai API Key？

**A**: 
1. 访问 [fal.ai](https://fal.ai/) 注册账号
2. 进入 Dashboard → API Keys
3. 创建新的 API Key 并复制到 `.env` 文件

### Q: FFmpeg 未找到怎么办？

**A**: 
1. 下载 [FFmpeg](https://ffmpeg.org/download.html)
2. 解压并将 `bin` 目录添加到系统 PATH
3. 重启终端，运行 `ffmpeg -version` 验证

### Q: 视频生成速度慢？

**A**: Kling API 生成视频需要一定时间（通常 30-90 秒/段），这是正常现象。可以：
- 减少 PPT 页数
- 使用更短的过渡时长

### Q: 支持其他图片格式吗？

**A**: 支持 PNG、JPG、JPEG 格式，建议使用 PNG 以保证最佳质量。

---

## 🛡️ 安全说明

- `.env` 文件已在 `.gitignore` 中，不会提交到 Git
- 请妥善保管 API Key，避免泄露
- 生成的视频内容版权请参考 fal.ai 服务条款

---

## 🤝 贡献指南

欢迎贡献代码和建议！

1. Fork 本项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

---

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

---

## 🙏 致谢

- [fal.ai](https://fal.ai/) - 提供 Kling 2.6 API 服务
- [Kling AI](https://klingai.com/) - 首尾帧视频生成技术
- [FFmpeg](https://ffmpeg.org/) - 强大的视频处理工具
- [NanoBanana-PPT-Skills](https://github.com/op7418/NanoBanana-PPT-Skills) - 项目灵感来源

---

**⭐ 如果这个项目对你有帮助，请给一个 Star！**

Made with ❤️ | Powered by Kling AI & FFmpeg
