from datetime import datetime

import httpx
from sqlalchemy import select

from ..db import SessionLocal
from ..models import Activity, ImportJob, ImportJobStatus, User
from .coverage import persist_track_and_new_coverage
from .strava import (
    activity_from_payload,
    iter_activity_pages,
    fetch_latlng_stream,
    get_authenticated_connection,
)


async def run_history_import(job_id: int, user_id: int) -> None:
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
        has_existing_activities = db.scalar(select(Activity.id).where(Activity.user_id == user.id).limit(1)) is not None
        consecutive_existing = 0

        async for batch in iter_activity_pages(connection):
            for payload in batch:
                job.activities_seen += 1
                existing = db.scalar(
                    select(Activity).where(
                        Activity.user_id == user.id,
                        Activity.strava_activity_id == payload["id"],
                    )
                )
                if existing:
                    consecutive_existing += 1
                    continue

                consecutive_existing = 0
                activity = activity_from_payload(user.id, payload)
                db.add(activity)
                db.flush()
                job.activities_imported += 1
                if activity.atlas_type and activity.has_gps:
                    points = await fetch_latlng_stream(connection, activity.strava_activity_id)
                    if persist_track_and_new_coverage(db, activity, points):
                        job.activities_with_new_coverage += 1
                db.commit()

            db.commit()
            if has_existing_activities and consecutive_existing >= 100:
                break

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
            job.error = str(exc)[:500]
            job.finished_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()
