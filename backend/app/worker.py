import asyncio
import os

from sqlalchemy import text

from .db import Base, engine
from .services.webhooks import process_pending_jobs


async def run_forever() -> None:
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(bind=engine)
    poll_seconds = float(os.getenv("WEBHOOK_WORKER_POLL_SECONDS", "5"))
    while True:
        await process_pending_jobs()
        await asyncio.sleep(poll_seconds)


if __name__ == "__main__":
    asyncio.run(run_forever())
