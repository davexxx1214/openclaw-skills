# TinyFish Skill

TinyFish Web Agent 独立技能（Python 版）。  
该技能通过自然语言驱动浏览器自动化，不依赖 CSS Selector / XPath，可直接用于网页采集、流程自动化与网页监控任务。

## 功能概览

- 同步调用接口：`/run`
- 流式调用接口：`/run-sse`
- 支持防检测参数：`browser_profile=stealth` + `proxy_config`
- 所有脚本独立放在 `skills/tinyfish/scripts/`
- API Key 从 `skills/tinyfish/.env` 读取（你已配置完成）

## 依赖安装

在项目根目录执行：

```bash
pip install requests python-dotenv
```

## 环境变量

`skills/tinyfish/.env` 中应包含：

```bash
TINYFISH_API_KEY=sk-tinyfish-*****
```

## 使用脚本

### 1) 联通测试（推荐先执行）

```bash
python skills/tinyfish/scripts/test_connection.py
```

用途：
- 验证 `.env` 是否可读取
- 验证 TinyFish `/run` 接口是否可访问
- 返回状态为 `COMPLETED` 视为联通成功

### 2) 同步模式调用

```bash
python skills/tinyfish/scripts/run_sync.py --url "https://example.com" --goal "Extract page title as JSON."
```

启用防检测：

```bash
python skills/tinyfish/scripts/run_sync.py --url "https://example.com" --goal "Extract page title as JSON." --stealth
```

### 3) 流式模式调用（实时进度）

```bash
python skills/tinyfish/scripts/run_sse.py --url "https://example.com" --goal "Extract page title as JSON."
```

启用防检测：

```bash
python skills/tinyfish/scripts/run_sse.py --url "https://example.com" --goal "Extract page title as JSON." --stealth
```

## 脚本结构

```text
skills/tinyfish/
├── .env
├── skill.md
└── scripts/
    ├── _tinyfish_client.py   # 公共客户端：读取 .env + 调用 TinyFish API
    ├── run_sync.py           # 同步调用示例
    ├── run_sse.py            # 流式调用示例
    └── test_connection.py    # 联通测试脚本
```

## 建议的提问模板（给调用方）

在自动生成任务前，先明确以下信息：

1. 任务类型
   - 数据提取 / 抓取
   - 表单自动化
   - 网站监控
   - AI Agent 网页浏览
2. 调用方式
   - 同步 `/run`
   - 流式 `/run-sse`
3. 是否需要防检测
   - 普通站点（不需要）
   - 有 Cloudflare/CAPTCHA/反爬（需要）
4. 输出格式
   - JSON 字段定义（尽量明确）

## 故障排查

1. 报错 `TINYFISH_API_KEY is missing`
   - 检查 `skills/tinyfish/.env` 文件是否存在且变量名正确
2. HTTP 401/403
   - 检查 API Key 是否有效、是否过期
3. 请求超时
   - 目标网页响应慢，换更轻量页面先验证
4. 返回非 `COMPLETED`
   - 优化 `goal` 描述，增加具体输出要求和步骤