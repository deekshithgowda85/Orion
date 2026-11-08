"""Temporal worker entrypoint: ``python worker.py``."""
import asyncio
import logging
import signal

from temporalio.worker import Worker

from activities.implementations import ALL_ACTIVITIES
from config import TASK_QUEUE, get_settings
from temporal_client import connect
from workflows.research_workflow import ResearchWorkflow

logger = logging.getLogger("worker")


async def main() -> None:
    """Connect to Temporal and run the worker until interrupted."""
    settings = get_settings()
    client = await connect()
    logger.info("Connected to Temporal at %s (namespace=%s)", settings.temporal_host, settings.temporal_namespace)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows: fall back to KeyboardInterrupt
            pass

    async with Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[ResearchWorkflow],
        activities=ALL_ACTIVITIES,
    ):
        logger.info("Worker polling task queue %r", TASK_QUEUE)
        await stop.wait()
    logger.info("Worker shut down cleanly")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
