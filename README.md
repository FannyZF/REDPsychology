# 心语视界 — 中小学生心理学内容智能生产系统

面向中小学生心理健康领域的全自动内容生产工具。每日从官方心理学信源收集最新资讯，通过 LLM 进行分类、梳理、汇总并提炼核心观点，自动生成 10-15 秒短视频，一键发布至小红书。

## 系统流程

```
官方信源抓取 → LLM 归类+观点提炼 → AI 视频生成 → 小红书发布
```

## 快速开始

### 1. 准备环境

- **Python 3.11+**
- **Docker** (推荐) 或本地运行
- **Deepseek API Key**
- **火山引擎(即梦) API Key** (ARK 开头)

### 2. Docker 部署 (推荐)

```bash
git clone <repo-url>
cd PsychologyContentStudio

# 编辑 .env 填入 API Keys
cp .env.example .env
# DEEPSEEK_API_KEY=sk-xxx
# VOLCENGINE_API_KEY=ark-xxx

# 启动服务
docker compose up -d --build
```

访问 `http://<服务器IP>:8998`

### 3. 首次配置

1. 打开设置页面 `/settings`，填入 Deepseek 和火山引擎 API Key
2. 打开信源页面 `/sources`，确认 3 个信源已启用
3. 打开登录页面 `/login`，扫码登录小红书账号

### 4. 手动运行

```bash
# 一键全流程
python -m src.main run

# 或分步执行
python -m src.main collect   # 抓取信源
python -m src.main process   # LLM 加工
python -m src.main video     # 生成视频
python -m src.main publish   # 发布到小红书
```

## CLI 命令

| 命令 | 功能 |
|------|------|
| `python -m src.main init` | 生成默认 config.yaml |
| `python -m src.main web` | 启动 Web 管理后台 + 定时器 |
| `python -m src.main run` | 单次全流程 |
| `python -m src.main collect` | 仅抓取信源 |
| `python -m src.main process` | 仅 LLM 加工 |
| `python -m src.main video` | 仅生成视频 |
| `python -m src.main publish` | 仅发布 (支持 --no-headless 手动扫码) |
| `python -m src.main backfill --days 30` | 历史回溯 |
| `python -m src.main schedule` | 仅定时器 (不启动 Web) |

## 定时调度

| 时间 | 任务 |
|------|------|
| 07:00 | 抓取信源 |
| 07:30 | LLM 加工 |
| 08:15 | AI 视频生成 |
| 18:00 | 小红书发布 |

## 项目结构

```
PsychologyContentStudio/
├── src/
│   ├── main.py           # CLI 入口
│   ├── collector/        # 信源采集 (scraper, dedup, selector_detect, orchestrator)
│   ├── processor/        # LLM 加工 (llm_client, prompt, pipeline)
│   ├── video_generator/  # 视频生成 (client, template, composer)
│   ├── publisher/        # 小红书发布 (selenium_publisher, publish_service)
│   ├── scheduler/        # 定时调度 (daily_pipeline, backfill)
│   ├── storage/          # 数据层 (models, db)
│   ├── web/              # Web 管理后台 (app + templates/)
│   └── utils/            # 工具类 (logger, key_store, config_store)
├── assets/music/         # 背景音乐 (4首)
├── output/               # 视频/截图/字幕/文案
├── data/                 # SQLite + JSON 配置
├── logs/                 # 运行日志
├── scripts/              # 辅助脚本
├── Dockerfile
├── docker-compose.yml
└── config.yaml
```

## 技术栈

- **语言**: Python 3.11+
- **爬虫**: httpx + BeautifulSoup4
- **LLM**: Deepseek (OpenAI SDK 兼容)
- **视频**: 火山引擎(即梦) + FFmpeg (字幕/音乐)
- **发布**: Selenium Chrome Headless
- **调度**: APScheduler
- **Web**: FastAPI + Jinja2 + Tailwind CSS
- **存储**: SQLite
- **部署**: Docker + docker-compose

## 环境变量

| 变量 | 说明 |
|------|------|
| DEEPSEEK_API_KEY | Deepseek API 密钥 |
| DEEPSEEK_BASE_URL | API 地址 (默认 https://api.deepseek.com) |
| VOLCENGINE_API_KEY | 火山引擎(即梦) API 密钥 (ARK 开头) |
| TZ | 时区 (Asia/Shanghai) |

## 月成本预估

| 项目 | 成本 |
|------|------|
| LLM 加工 (Deepseek) | ~¥30/月 |
| 视频生成 (火山引擎) | ~¥200-400/月 |
| **合计** | **约 ¥250-450/月** |
