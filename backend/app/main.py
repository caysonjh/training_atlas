import hashlib
import hmac
import time

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from .auth import create_session_token, get_current_user
from .config import settings
from .db import Base, SessionLocal, engine, get_db
from .models import Activity, ImportJob, ImportJobStatus, PhotoMarker, StravaWebhookJob, User, WebhookJobStatus
from .schemas import ActivityOut, ImportJobOut, MapStatsOut, PhotoOut, StravaStatusOut
from .services.strava import exchange_code, oauth_url, upsert_user_and_connection

app = FastAPI(title="Atlas API")
local_dev_origins = {
    settings.frontend_url,
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(local_dev_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    if settings.bootstrap_postgis_extension:
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    if settings.create_tables_on_startup:
        Base.metadata.create_all(bind=engine)
    if settings.recover_jobs_on_startup:
        with SessionLocal() as db:
            db.execute(
                update(ImportJob)
                .where(ImportJob.status.in_([ImportJobStatus.pending, ImportJobStatus.running]))
                .values(status=ImportJobStatus.failed, error="Interrupted by backend restart")
            )
            db.execute(
                update(StravaWebhookJob)
                .where(StravaWebhookJob.status == WebhookJobStatus.running)
                .values(status=WebhookJobStatus.pending, error="Recovered after worker restart")
            )
            db.commit()


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/auth/strava/connect")
def connect_strava():
    return {"url": oauth_url()}


@app.get("/auth/strava/status", response_model=StravaStatusOut)
def strava_status(current_user: User = Depends(get_current_user)):
    return StravaStatusOut(
        connected=current_user.strava_connection is not None,
        athlete_name=current_user.display_name if current_user.strava_connection else None,
        athlete_id=current_user.strava_athlete_id if current_user.strava_connection else None,
    )


@app.get("/auth/strava/callback")
async def strava_callback(code: str, db: Session = Depends(get_db)):
    payload = await exchange_code(code)
    user = upsert_user_and_connection(db, payload)
    response = RedirectResponse(settings.frontend_url)
    response.set_cookie(
        key="session",
        value=create_session_token(user.id),
        httponly=True,
        samesite=settings.session_cookie_samesite,
        secure=settings.session_cookie_secure,
    )
    return response


def _latest_active_import_job(db: Session, user_id: int) -> ImportJob | None:
    return db.scalar(
        select(ImportJob)
        .where(
            ImportJob.user_id == user_id,
            ImportJob.status.in_([ImportJobStatus.pending, ImportJobStatus.running]),
        )
        .order_by(ImportJob.created_at.desc())
        .limit(1)
    )


def _latest_import_job(db: Session, user_id: int) -> ImportJob | None:
    return db.scalar(select(ImportJob).where(ImportJob.user_id == user_id).order_by(ImportJob.created_at.desc()).limit(1))


def _create_import_job(db: Session, user_id: int) -> ImportJob:
    job = ImportJob(user_id=user_id)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@app.post("/sync/strava", response_model=ImportJobOut)
async def sync_strava(
    background_tasks: BackgroundTasks,
    full: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    active_job = _latest_active_import_job(db, current_user.id)
    if active_job:
        return active_job
    job = _create_import_job(db, current_user.id)
    from .services.imports import run_strava_sync

    background_tasks.add_task(run_strava_sync, job.id, current_user.id, full=full)
    return job


@app.get("/sync/strava/latest", response_model=ImportJobOut | None)
def latest_sync(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _latest_import_job(db, current_user.id)


@app.post("/imports/strava/history", response_model=ImportJobOut)
async def import_history(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await sync_strava(background_tasks, True, db, current_user)


@app.get("/imports/strava/history/latest", response_model=ImportJobOut | None)
def latest_import(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _latest_import_job(db, current_user.id)


@app.get("/map/coverage")
def get_coverage(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from .services.coverage_sql import coverage_feature_collection

    return coverage_feature_collection(db, current_user.id)


@app.get("/map/stats", response_model=MapStatsOut)
def get_map_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from .services.coverage_sql import total_unique_distance_meters

    return MapStatsOut(total_unique_distance_meters=total_unique_distance_meters(db, current_user.id))


@app.get("/activities", response_model=list[ActivityOut])
def list_activities(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.scalars(
        select(Activity).where(Activity.user_id == current_user.id).order_by(Activity.started_at.desc()).limit(100)
    ).all()


@app.post("/photos", response_model=PhotoOut)
async def create_photo(
    longitude: float = Form(...),
    latitude: float = Form(...),
    caption: str | None = Form(default=None),
    activity_id: int | None = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if activity_id:
        activity = db.get(Activity, activity_id)
        if not activity or activity.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Activity not found")
    from .services.storage import upload_photo

    image_url = await upload_photo(file)
    marker = PhotoMarker(
        user_id=current_user.id,
        activity_id=activity_id,
        image_url=image_url,
        caption=caption,
        longitude=longitude,
        latitude=latitude,
    )
    db.add(marker)
    db.commit()
    db.refresh(marker)
    return marker


@app.get("/photos", response_model=list[PhotoOut])
def list_photos(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.scalars(select(PhotoMarker).where(PhotoMarker.user_id == current_user.id)).all()


@app.get("/webhooks/strava")
def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):
    if hub_mode != "subscribe" or hub_verify_token != settings.strava_verify_token:
        raise HTTPException(status_code=403, detail="Verification failed")
    return {"hub.challenge": hub_challenge}


def _verify_strava_signature(raw_body: bytes, header: str | None) -> bool:
    if not settings.strava_webhook_secret:
        return True
    if not header:
        return False
    try:
        parts = dict(part.split("=", 1) for part in header.split(","))
        timestamp = parts["t"]
        signature = parts["v1"]
    except (KeyError, ValueError):
        return False
    if abs(time.time() - int(timestamp)) > 300:
        return False
    signed_payload = timestamp.encode() + b"." + raw_body
    expected = hmac.new(settings.strava_webhook_secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


@app.post("/webhooks/strava")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    raw_body = await request.body()
    if not _verify_strava_signature(raw_body, request.headers.get("X-Strava-Signature")):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    event = await request.json()
    from .services.webhooks import enqueue_webhook_job, process_pending_jobs

    job = enqueue_webhook_job(db, event)
    if job and settings.embedded_webhook_worker:
        background_tasks.add_task(process_pending_jobs, 1)
    return Response(status_code=200)
