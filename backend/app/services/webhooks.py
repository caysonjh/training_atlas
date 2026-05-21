from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Activity, StravaWebhookJob, User, WebhookJobStatus
from .coverage_sql import persist_track_and_new_coverage
from .strava import activity_from_payload, fetch_activity, fetch_latlng_stream, get_authenticated_connection


def event_key_for(event: dict) -> str:
    return ":".join(
        str(event.get(field, ""))
        for field in ("subscription_id", "object_type", "object_id", "aspect_type", "event_time")
    )


def accepts_create_activity(event: dict) -> bool:
    return event.get("object_type") == "activity" and event.get("aspect_type") == "create"


def enqueue_webhook_job(db: Session, event: dict) -> StravaWebhookJob | None:
    if not accepts_create_activity(event):
        return None
    owner_id = event.get("owner_id")
    object_id = event.get("object_id")
    if not isinstance(owner_id, int) or not isinstance(object_id, int):
        return None

    user = db.scalar(select(User).where(User.strava_athlete_id == owner_id))
    job = StravaWebhookJob(
        event_key=event_key_for(event),
        user_id=user.id if user else None,
        owner_id=owner_id,
        object_id=object_id,
        object_type=event["object_type"],
        aspect_type=event["aspect_type"],
        subscription_id=event.get("subscription_id"),
        event_time=event.get("event_time"),
        payload=event,
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return db.scalar(select(StravaWebhookJob).where(StravaWebhookJob.event_key == event_key_for(event)))
    db.refresh(job)
    return job


async def process_webhook_job(db: Session, job: StravaWebhookJob) -> None:
    if job.status not in {WebhookJobStatus.pending, WebhookJobStatus.failed}:
        return
    job.status = WebhookJobStatus.running
    job.attempts += 1
    job.started_at = datetime.utcnow()
    db.commit()

    try:
        user = db.get(User, job.user_id) if job.user_id else None
        if not user:
            job.status = WebhookJobStatus.skipped
            job.error = "Unknown Strava athlete"
            return

        existing = db.scalar(
            select(Activity).where(Activity.user_id == user.id, Activity.strava_activity_id == job.object_id)
        )
        if existing:
            job.status = WebhookJobStatus.completed
            return

        connection = await get_authenticated_connection(db, user)
        payload = await fetch_activity(connection, job.object_id)
        activity = activity_from_payload(user.id, payload)
        db.add(activity)
        db.flush()

        if activity.is_private:
            job.status = WebhookJobStatus.skipped
            job.error = "Private activity"
            return
        if not activity.atlas_type:
            job.status = WebhookJobStatus.skipped
            job.error = "Unsupported sport or non-geographic swim"
            return
        if not activity.has_gps:
            job.status = WebhookJobStatus.skipped
            job.error = "Activity has no GPS"
            return

        points = await fetch_latlng_stream(connection, activity.strava_activity_id)
        persist_track_and_new_coverage(db, activity, points)
        job.status = WebhookJobStatus.completed
    except httpx.HTTPStatusError as exc:
        job.status = WebhookJobStatus.failed
        job.error = f"Strava returned {exc.response.status_code}"
    except Exception as exc:
        job.status = WebhookJobStatus.failed
        job.error = str(exc)[:500]
    finally:
        job.finished_at = datetime.utcnow()
        db.commit()


async def process_pending_jobs(limit: int = 25) -> int:
    db = SessionLocal()
    processed = 0
    try:
        jobs = db.scalars(
            select(StravaWebhookJob)
            .where(StravaWebhookJob.status == WebhookJobStatus.pending)
            .order_by(StravaWebhookJob.created_at.asc())
            .limit(limit)
        ).all()
        for job in jobs:
            await process_webhook_job(db, job)
            processed += 1
        return processed
    finally:
        db.close()
