"""Standalone worker: `python -m app.workers.run` (use this in production with EMBEDDED_WORKER=false on the API)."""

import asyncio
import signal

from app.core.config import get_settings
from app.core.database import dispose_engine
from app.core.logging import configure_logging
from app.workers.runner import worker_loop


async def main() -> None:
    configure_logging(get_settings().app_env)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await worker_loop(stop)
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
