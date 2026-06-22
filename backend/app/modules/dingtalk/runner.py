"""钉钉 Stream Consumer 独立进程入口。

必须独立进程运行（不接入 FastAPI lifespan，避免 uvicorn 多 worker 重复连接）：

    cd /srv/huabang-ai-center/backend
    .venv/bin/python -m app.modules.dingtalk.runner [--force-test]

启用与否由 systemd / DINGTALK_STREAM_ENABLED 控制；--force-test 用于前台联调。
"""
import argparse
import logging
import sys

from app.core.config import settings
from app.core.logger import setup_logging
from app.modules.dingtalk.stream_client import build_client

logger = logging.getLogger("dingtalk.stream")


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="DingTalk Stream consumer")
    parser.add_argument(
        "--force-test",
        action="store_true",
        help="忽略 DINGTALK_STREAM_ENABLED，前台强制试运行",
    )
    args = parser.parse_args()

    print("DingTalk Stream consumer starting...")

    # 凭证缺失：只提示，不输出任何真实值
    if not settings.DINGTALK_CLIENT_ID or not settings.DINGTALK_CLIENT_SECRET:
        logger.error("配置缺失：DingTalk Stream credentials missing")
        sys.exit(1)

    if not settings.DINGTALK_STREAM_ENABLED and not args.force_test:
        logger.warning(
            "DINGTALK_STREAM_ENABLED=false，未启用钉钉 Stream Consumer"
            "（可加 --force-test 前台测试，或由 systemd 启用），退出。"
        )
        sys.exit(0)

    logger.info("启动钉钉 Stream Consumer ...")
    client = build_client()
    # 阻塞运行：SDK 内部自管 asyncio 事件循环、心跳与断线重连
    client.start_forever()


if __name__ == "__main__":
    main()
