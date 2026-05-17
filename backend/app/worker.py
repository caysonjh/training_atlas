import asyncio
from sqlalchemy import text

from .config import settings
from .db import Base, engine
from .services.webhooks import process_pending_jobs


async def run_forever() -> None:
    if settings.bootstrap_postgis_extension:
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(bind=engine)
    poll_seconds = settings.webhook_worker_poll_seconds
    while True:
        await process_pending_jobs()
        await asyncio.sleep(poll_seconds)


if __name__ == "__main__":
    asyncio.run(run_forever())
