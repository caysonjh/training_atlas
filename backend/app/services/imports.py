from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func, select

from ..config import settings
from ..db import SessionLocal
from ..models import Activity, ImportJob, ImportJobStatus, User
from .coverage_sql import persist_track_and_new_coverage
from .strava import (
    activity_from_payload,
    fetch_latlng_stream,
    get_authenticated_connection,
    iter_activity_pages,
)


def _as_utc_timestamp(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp())


def _incremental_after_timestamp(db, user_id: int) -> int | None:
    latest_started_at = db.scalar(select(func.max(Activity.started_at)).where(Activity.user_id == user_id))
    if latest_started_at is None:
        return None
    overlap_start = latest_started_at - timedelta(days=settings.strava_sync_overlap_days)
    return _as_utc_timestamp(overlap_start)


async def run_strava_sync(job_id: int, user_id: int, *, full: bool = False) -> None:
    db = SessionLocal()
    try:
        job = db.get(ImportJob, job_id)
        user = db.get(User, user_id)
        if not job or not user:
            return
        job.status = ImportJobStatus.running
        job.started_at = datetime.utcnow()
        db.commit()

        connection = await get_authenticated_connection(db, user)
        after = None if full else _incremental_after_timestamp(db, user.id)

        async for batch in iter_activity_pages(connection, per_page=settings.strava_import_page_size, after=after):
            for payload in batch:
                activity_id = payload.get("id")
                try:
                    job.activities_seen += 1
                    existing = db.scalar(
                        select(Activity).where(
                            Activity.user_id == user.id,
                            Activity.strava_activity_id == activity_id,
                        )
                    )
                    if existing:
                        db.commit()
                        continue

                    activity = activity_from_payload(user.id, payload)
                    db.add(activity)
                    db.flush()
                    job.activities_imported += 1
                    if activity.atlas_type and activity.has_gps:
                        points = await fetch_latlng_stream(connection, activity.strava_activity_id)
                        if persist_track_and_new_coverage(db, activity, points):
                            job.activities_with_new_coverage += 1
                    db.commit()
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code in {401, 429}:
                        raise
                    db.rollback()
                    job = db.get(ImportJob, job_id)
                    if job:
                        job.error = f"Skipped Strava activity {activity_id}: Strava returned {exc.response.status_code}"[:500]
                        db.commit()
                except (httpx.TimeoutException, SQLAlchemyError, ValueError, KeyError) as exc:
                    db.rollback()
                    job = db.get(ImportJob, job_id)
                    if job:
                        job.error = f"Skipped Strava activity {activity_id}: {type(exc).__name__}: {str(exc) or repr(exc)}"[:500]
                        db.commit()

            db.commit()

        job.status = ImportJobStatus.completed
        job.finished_at = datetime.utcnow()
        db.commit()
    except httpx.HTTPStatusError as exc:
        job = db.get(ImportJob, job_id)
        if job:
            job.status = ImportJobStatus.failed
            job.error = f"Strava returned {exc.response.status_code}"
            job.finished_at = datetime.utcnow()
            db.commit()
    except Exception as exc:
        job = db.get(ImportJob, job_id)
        if job:
            job.status = ImportJobStatus.failed
            job.error = f"{type(exc).__name__}: {str(exc) or repr(exc)}"[:500]
            job.finished_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


async def run_history_import(job_id: int, user_id: int) -> None:
    await run_strava_sync(job_id, user_id, full=True)
