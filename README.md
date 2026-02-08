# OpenClaw Skills

OpenClaw 的技能集合 — 一组即装即用的 AI Agent Skills，覆盖金融交易、多媒体生产、视频生成、信息检索等场景。每个目录对应一个独立可复用的技能，配有完整的脚本、配置模板和使用文档。

## 总览

| Skill | 简介 | 关键技术 |
|-------|------|----------|
| [alpaca-live-trading](#alpaca-live-trading) | 美股实时交易决策数据工具集 | AlphaVantage, Alpaca API, Polymarket |
| [dynamic-slides](#dynamic-slides) | PPT 图片序列转动态转场视频 | Kling AI (fal.ai), FFmpeg |
| [find-skills](#find-skills) | 发现与安装开放技能生态中的 Skills | Skills CLI (`npx skills`) |
| [listenhub](#listenhub) | 多媒体内容生产（播客/解说视频/TTS/图片） | ListenHub API, Labnana API |
| [polymarket](#polymarket) | 查询 Polymarket 预测市场数据 | Polymarket Gamma API |
| [telegram-offline-voice](#telegram-offline-voice) | 本地生成 Telegram 语音消息 | Edge-TTS, FFmpeg |
| [veo3-video-gen](#veo3-video-gen) | 文本生成视频与多段拼接 | Google Veo 3.x, Gemini API |
| [yahoo-finance-cli](#yahoo-finance-cli) | Yahoo Finance 行情与财务数据查询 | yahoo-finance2 CLI, jq |
| [yt-dlp-downloader-skill](#yt-dlp-downloader-skill) | 多平台视频/音频/字幕下载 | yt-dlp, FFmpeg |

---

## Skills 详细介绍

### alpaca-live-trading

**美股实时交易决策数据工具集** — 使用 Alpaca Paper Trading 进行模拟交易决策。

提供一组独立的 Python 查询脚本，无需 MCP 服务即可运行，用于获取交易决策所需的各类数据：

- **股价查询** — 通过 AlphaVantage API 获取 NASDAQ 100 成分股的实时价格
- **市场新闻** — 获取市场新闻和情绪分析，支持按股票代码、主题过滤
- **市场情绪** — 通过 Polymarket 获取预测市场情绪指标
- **账户状态** — 查询 Alpaca 模拟交易账户的持仓与余额

**依赖：** `pip install requests pyyaml alpaca-py`
**配置：** 需要 AlphaVantage 和 Alpaca 的 API Key，通过 `config.yaml` 管理

---

### dynamic-slides

**PPT 动态转场视频生成器** — 将 PPT 导出的图片序列通过 Kling AI 的首尾帧技术转换为动态过渡视频。

**核心流程：**
1. 将 PPT 导出的图片（PNG/JPG）放入 `PPT/` 目录
2. 运行 `python main.py` 启动转换
3. 自动调用 fal.ai 上的 Kling API 生成转场片段
4. FFmpeg 拼接为最终的 `final.mp4`

**依赖：** `pip install -r requirements.txt`，系统需安装 FFmpeg
**配置：** 需要在 `.env` 中设置 `FAL_KEY`

---

### find-skills

**技能发现与安装助手** — 帮助用户从开放 Agent Skills 生态中搜索、发现和安装技能。

**核心命令：**
```bash
npx skills find [query]    # 搜索技能
npx skills add <package>   # 安装技能
npx skills check           # 检查更新
npx skills update          # 更新所有技能
```

**浏览技能市场：** https://skills.sh/

支持按领域搜索：Web 开发、测试、DevOps、文档、代码质量、设计、效率工具等。

---

### listenhub

**多媒体内容生产工具** — 输入内容，输出音频/视频/图片，支持四种模式：

| 模式 | 用途 | 预计耗时 |
|------|------|----------|
| **Podcast（播客）** | 单人/双人对话，适合深度讨论 | 2-3 分钟 |
| **Explain（解说视频）** | 单人旁白 + AI 画面，适合产品介绍 | 3-5 分钟 |
| **TTS（文字转语音）** | 纯语音朗读，适合文章转音频 | 1-2 分钟 |
| **Image（图片生成）** | AI 图片生成，适合创意可视化 | 即时 |

**输入支持：** 主题描述、YouTube 链接、文章 URL、纯文本、图片提示词
**依赖：** 系统需安装 `curl` 和 `jq`
**配置：** 需要 `LISTENHUB_API_KEY` 环境变量（从 https://listenhub.ai/settings/api-keys 获取）

---

### polymarket

**Polymarket 预测市场查询工具** — 查询全球预测市场的赔率、趋势和事件信息。

**支持的查询：**
```bash
python3 polymarket/scripts/polymarket.py trending              # 热门市场
python3 polymarket/scripts/polymarket.py search "bitcoin"      # 搜索市场
python3 polymarket/scripts/polymarket.py event "fed-decision"  # 特定事件
python3 polymarket/scripts/polymarket.py category politics     # 按分类查询
```

**输出信息：** 问题/标题、当前赔率（Yes/No 价格）、交易量、截止日期
**特点：** 使用公开的 Gamma API，无需认证即可读取（只读模式，不支持交易）

---

### telegram-offline-voice

**Telegram 离线语音消息生成器** — 使用 Microsoft Edge-TTS 本地生成高质量语音，零成本、无需任何 API Token。

**特性：**
- 完全本地处理，无需云服务
- Edge-TTS 免费使用，无调用限制
- 默认使用微软晓晓（zh-CN-XiaoxiaoNeural）高质量声线
- 输出 OGG Opus 格式，Telegram 原生语音气泡显示

**使用示例：**
```bash
# 1. 生成原始音频
edge-tts --voice zh-CN-XiaoxiaoNeural --rate=+5% --text "你好" --write-media raw.mp3
# 2. 转为 Telegram 语音格式
ffmpeg -y -i raw.mp3 -c:a libopus -b:a 48k -ac 1 -ar 48000 -application voip voice.ogg
```

**依赖：** `pip install edge-tts`，系统需安装 FFmpeg

---

### veo3-video-gen

**Veo 3 文本生成视频工具** — 基于 Google Gemini API 的 Veo 3.x 模型，从文本提示生成 MP4 视频，支持多段拼接生成长视频。

**基本用法：**
```bash
uv run scripts/generate_video.py \
  --prompt "A close up of ..." \
  --filename "out.mp4" \
  --model "veo-3.1-generate-preview" \
  --aspect-ratio "9:16"
```

**多段拼接：** 通过 `--segments` 参数生成多个片段并用 FFmpeg 自动拼接，支持 `--base-style` 保持风格一致性，`--use-last-frame` 提取上一段末帧以确保画面连续性。

**依赖：** 需要 `GEMINI_API_KEY` 环境变量，多段拼接需要 FFmpeg

---

### yahoo-finance-cli

**Yahoo Finance 命令行数据工具** — 通过 `yf` 命令获取实时行情、财务基本面、分析师评级和趋势数据。

**支持的查询模块：**
| 模块 | 用途 | 示例 |
|------|------|------|
| `quote` | 实时价格与涨跌 | `yf quote AAPL` |
| `quoteSummary` | 财务基本面详情 | `yf quoteSummary AAPL '{"modules":["financialData"]}'` |
| `insights` | 估值与技术分析 | `yf insights AAPL` |
| `search` | 搜索股票代码 | `yf search "Apple"` |
| `chart` | 历史 K 线数据 | `yf chart AAPL '{"period1":"2024-01-01"}'` |
| `trendingSymbols` | 热门股票 | `yf trendingSymbols US` |

**依赖：** Node.js、`yahoo-finance2`（npm）、`jq`

---

### yt-dlp-downloader-skill

**多平台视频下载器** — 使用 yt-dlp 从 YouTube、Bilibili、Twitter/X、TikTok 等数千个网站下载视频、音频和字幕。

**常用功能：**
| 功能 | 命令 |
|------|------|
| 下载最佳质量视频 | `yt-dlp -P "~/Downloads/yt-dlp" "URL"` |
| 提取 MP3 音频 | `yt-dlp -x --audio-format mp3 "URL"` |
| 下载字幕 | `yt-dlp --write-subs --sub-langs all "URL"` |
| 指定 720p | `yt-dlp -f "bestvideo[height<=720]+bestaudio" "URL"` |
| 查看可用格式 | `yt-dlp -F "URL"` |
| 下载播放列表 | `yt-dlp -I 1:5 "PLAYLIST_URL"` |

**提示：** YouTube 下载建议始终加 `--cookies-from-browser chrome` 以避免 403 错误
**依赖：** `pip install yt-dlp`，音频提取需要 FFmpeg
