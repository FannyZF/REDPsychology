import asyncio
import argparse
import sys
import os
import yaml
from pathlib import Path


ROOT_DIR = Path(__file__).parent.parent
DEFAULT_CONFIG_PATH = ROOT_DIR / "config.yaml"

DEFAULT_CONFIG = {
    "sources": [
        {
            "name": "教育部",
            "base_url": "https://www.moe.gov.cn",
            "list_url": "https://www.moe.gov.cn/jyb_xwfb/",
            "enabled": True,
            "content_type": "policy",
            "credibility": "official",
            "selectors": {
                "list_container": "div.news_list li",
                "title": "a",
                "link": "a",
                "date": "span.date",
            },
            "article_selector": {"content": "div.article_content"},
            "pagination": {"pattern": "/jyb_xwfb/index_{page}.html", "start": 1},
        },
        {
            "name": "中国心理学会",
            "base_url": "https://www.cpsbeijing.org",
            "list_url": "https://www.cpsbeijing.org/cms/show.action?category_id=3",
            "enabled": True,
            "content_type": "academic",
            "credibility": "academic",
            "selectors": {
                "list_container": "ul.news-list li",
                "title": "h4 a",
                "link": "h4 a",
                "date": "span.time",
            },
            "article_selector": {"content": "div.content"},
            "pagination": {
                "pattern": "/cms/show.action?category_id=3&pageNo={page}",
                "start": 1,
            },
        },
        {
            "name": "中国教育科学研究院",
            "base_url": "https://www.nies.net.cn",
            "list_url": "https://www.nies.net.cn/xwzx/",
            "enabled": True,
            "content_type": "research",
            "credibility": "research",
            "selectors": {
                "list_container": "div.news-con ul li",
                "title": "a",
                "link": "a",
                "date": "span",
            },
            "article_selector": {"content": "div.TRS_Editor"},
            "pagination": {"pattern": "/xwzx/index_{page}.html", "start": 1},
        },
    ],
    "llm": {
        "provider": "deepseek",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
        "temperature_process": 0.3,
        "temperature_content": 0.7,
        "max_tokens": 4096,
    },
    "video": {
        "provider": "volcengine",
        "default_duration": 15,
        "aspect_ratio": "9:16",
        "max_generate_per_run": 3,
        "default_template": "清新治愈",
    },
    "publish": {
        "max_per_day": 1,
        "publish_hour": 18,
        "publish_minute": 0,
        "publish_window_minutes": 30,
    },
    "collection": {
        "lookback_days": 1,
        "max_concurrent_sources": 3,
        "request_timeout": 30,
    },
}


def cmd_init(args):
    """生成默认 config.yaml"""
    config_path = Path(args.config) if args.config else DEFAULT_CONFIG_PATH
    if config_path.exists():
        if not args.force:
            response = input(f"{config_path} 已存在，是否覆盖? (y/N): ")
            if response.lower() != "y":
                print("取消初始化。")
                return
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(DEFAULT_CONFIG, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print(f"已生成默认配置: {config_path}")


def cmd_web(args):
    import uvicorn
    from src.scheduler.daily_pipeline import setup_scheduler
    scheduler = setup_scheduler()
    scheduler.start()
    print("Web 管理后台启动: http://127.0.0.1:8998")
    print("定时器已启动 (采集07:00 加工07:30 封面08:15 发布18:00)")
    try:
        uvicorn.run("src.web.app:app", host="0.0.0.0", port=8998)
    except KeyboardInterrupt:
        scheduler.shutdown()
        print("服务已停止")


def cmd_run(args):
    from src.collector.orchestrator import collect_all, load_config
    from src.processor.llm_client import LLMClient
    from src.processor.pipeline import ProcessingPipeline
    from src.storage.db import ContentStore

    config = load_config(args.config) if args.config else load_config()
    store = ContentStore()

    print("=== 步骤1: 采集信源 ===")
    col_result = asyncio.run(collect_all(config))
    print(f"采集完成: 新增 {col_result['total_new']} 篇")

    pending = store.get_pending(limit=50)
    if pending:
        print(f"\n=== 步骤2: LLM加工 ({len(pending)}篇) ===")
        client = LLMClient()
        pipeline = ProcessingPipeline(client, store)
        proc_result = asyncio.run(pipeline.process_batch(pending))
        print(f"加工完成: 成功 {proc_result['success']} 篇, Token: {client.total_tokens}")
    else:
        print("没有待处理内容")

    processed = store.get_processed(limit=3)
    if processed:
        print(f"\n=== 步骤3: 封面生成 ({len(processed)}篇) ===")
        from src.video_generator.cover import generate_cover
        for item in processed:
            path = await generate_cover(item.id[:8], item.xhs_title or item.title, item.topic_category)
            if path:
                store.update_video_status(item.id, path, 0)
        print(f"封面生成完成")
    else:
        print("没有待生成封面的内容")

    queue = store.get_publish_queue(limit=1)
    if queue:
        print(f"\n=== 步骤4: 小红书发布 ===")
        from src.publisher.selenium_publisher import XiaohongshuPublisher
        from src.publisher.publish_service import ContentPublisher, PublishScheduler
        scheduler = PublishScheduler(store)
        can, reason = scheduler.can_publish_now()
        if not can:
            print(f"跳过发布: {reason}")
        else:
            xhs = XiaohongshuPublisher(headless=True)
            publisher = ContentPublisher(xhs, store)
            try:
                xhs.start()
                if xhs.ensure_login():
                    publisher.publish_one(queue[0])
            finally:
                xhs.close()
    else:
        print("没有待发布内容")

    print("\n=== 全流程完成 ===")


def cmd_collect(args):
    from src.collector.orchestrator import collect_all, load_config
    config = load_config(args.config) if args.config else load_config()
    result = asyncio.run(collect_all(config))
    print(f"采集完成: 新增 {result['total_new']} 篇, 跳过 {result['total_skipped']} 篇")
    if result["errors"]:
        for e in result["errors"]:
            print(f"  [错误] {e['source']}: {e['error']}")


def cmd_process(args):
    from src.processor.llm_client import LLMClient
    from src.processor.pipeline import ProcessingPipeline
    from src.storage.db import ContentStore

    store = ContentStore()
    client = LLMClient()
    pipeline = ProcessingPipeline(client, store)

    pending = store.get_pending(limit=50)
    if not pending:
        print("没有待处理的内容")
        return

    print(f"开始处理 {len(pending)} 篇待处理内容...")
    result = asyncio.run(pipeline.process_batch(pending))
    print(f"处理完成: 成功 {result['success']} 篇, 失败 {result['failed']} 篇")
    print(f"Token 用量: {client.total_tokens}")


def cmd_video(args):
    from src.video_generator.cover import generate_cover
    from src.storage.db import ContentStore
    store = ContentStore()
    processed = store.get_processed(limit=3)
    success = 0
    for item in processed:
        path = asyncio.run(generate_cover(item.id[:8], item.xhs_title or item.title, item.topic_category))
        if path:
            store.update_video_status(item.id, path, 0)
            success += 1
    print(f"封面生成完成: 成功 {success} 个")


def cmd_publish(args):
    from src.publisher.selenium_publisher import XiaohongshuPublisher
    from src.publisher.publish_service import ContentPublisher, PublishScheduler
    from src.storage.db import ContentStore

    store = ContentStore()
    scheduler = PublishScheduler(store)

    can, reason = scheduler.can_publish_now()
    if not can:
        print(f"当前不可发布: {reason}")
        return

    items = store.get_publish_queue(limit=1)
    if not items:
        print("待发布队列为空")
        return

    print("启动浏览器 (Headless)...")
    xhs = XiaohongshuPublisher(headless=args.no_headless is False)
    publisher = ContentPublisher(xhs, store)

    try:
        xhs.start()
        if not xhs.ensure_login():
            print("登录失败! 请检查截图 output/screenshots/ 或使用 --no-headless 手动扫码")
            return
        ok = publisher.publish_one(items[0])
        print(f"发布结果: {'成功' if ok else '失败'}")
    finally:
        xhs.close()


def cmd_backfill(args):
    from src.scheduler.backfill import backfill
    print(f"历史回溯 (从 {args.start_date or '30天前'} 起 {args.days} 天)...")
    result = asyncio.run(backfill(
        config_path=args.config,
        start_date=args.start_date,
        days=args.days,
    ))
    print(f"回溯完成: 新增 {result['total_new']} 篇, 错误 {result['total_errors']} 个")


def cmd_schedule(args):
    from src.scheduler.daily_pipeline import setup_scheduler
    import time
    scheduler = setup_scheduler()
    scheduler.start()
    print("定时器已启动 (Ctrl+C 停止)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        scheduler.shutdown()
        print("定时器已停止")


def main():
    parser = argparse.ArgumentParser(
        description="心语视界 - 中小学生心理学内容智能生产系统"
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    p_init = subparsers.add_parser("init", help="生成默认 config.yaml")
    p_init.add_argument("--config", default=None, help="配置文件路径")
    p_init.add_argument("--force", action="store_true", help="强制覆盖已有配置")
    p_init.set_defaults(func=cmd_init)

    p_web = subparsers.add_parser("web", help="启动 Web 管理后台 + 定时器")
    p_web.set_defaults(func=cmd_web)

    p_run = subparsers.add_parser("run", help="单次全流程 (抓取→加工→封面→发布)")
    p_run.add_argument("--config", default=None, help="配置文件路径")
    p_run.set_defaults(func=cmd_run)

    p_collect = subparsers.add_parser("collect", help="仅抓取信源资讯")
    p_collect.add_argument("--config", default=None, help="配置文件路径")
    p_collect.set_defaults(func=cmd_collect)

    p_process = subparsers.add_parser("process", help="仅 LLM 加工处理")
    p_process.set_defaults(func=cmd_process)

    p_video = subparsers.add_parser("video", help="仅为已加工内容生成封面")
    p_video.set_defaults(func=cmd_video)

    p_publish = subparsers.add_parser("publish", help="仅发布待发布内容")
    p_publish.add_argument("--no-headless", action="store_true", help="非headless模式, 可手动扫码")
    p_publish.set_defaults(func=cmd_publish)

    p_backfill = subparsers.add_parser("backfill", help="历史回溯抓取")
    p_backfill.add_argument("--start-date", default=None, help="起始日期 YYYY-MM-DD")
    p_backfill.add_argument("--days", type=int, default=30, help="回溯天数")
    p_backfill.set_defaults(func=cmd_backfill)

    p_schedule = subparsers.add_parser("schedule", help="仅启动定时器 (不启动 Web)")
    p_schedule.set_defaults(func=cmd_schedule)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
    else:
        args.func(args)


if __name__ == "__main__":
    main()
