import enum
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class ActivityType(str, enum.Enum):
    road_cycling = "road_cycling"
    mountain_biking = "mountain_biking"
    gravel_biking = "gravel_biking"
    running = "running"
    trail_running = "trail_running"
    open_water_swimming = "open_water_swimming"


class Visibility(str, enum.Enum):
    private = "private"
    friends = "friends"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    strava_athlete_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    display_name: Mapped[str] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(1024))
    default_visibility: Mapped[Visibility] = mapped_column(Enum(Visibility), default=Visibility.private)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    strava_connection: Mapped["StravaConnection"] = relationship(back_populates="user", uselist=False)


class StravaConnection(Base):
    __tablename__ = "strava_connections"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    access_token: Mapped[str] = mapped_column(String(512))
    refresh_token: Mapped[str] = mapped_column(String(512))
    expires_at: Mapped[int]
    scope: Mapped[str] = mapped_column(String(255))
    user: Mapped[User] = relationship(back_populates="strava_connection")


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (UniqueConstraint("user_id", "strava_activity_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    strava_activity_id: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(String(255))
    sport_type: Mapped[str] = mapped_column(String(80))
    atlas_type: Mapped[ActivityType | None] = mapped_column(Enum(ActivityType), nullable=True)
    started_at: Mapped[datetime]
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    has_gps: Mapped[bool] = mapped_column(Boolean, default=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RawTrack(Base):
    __tablename__ = "raw_tracks"

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), unique=True)
    geometry: Mapped[str] = mapped_column(Geometry("LINESTRING", srid=4326))


class CapturedGeometry(Base):
    __tablename__ = "captured_geometries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    atlas_type: Mapped[ActivityType] = mapped_column(Enum(ActivityType), index=True)
    source_activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"))
    geometry: Mapped[str] = mapped_column(Geometry("MULTILINESTRING", srid=4326))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PhotoMarker(Base):
    __tablename__ = "photo_markers"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    activity_id: Mapped[int | None] = mapped_column(ForeignKey("activities.id"))
    image_url: Mapped[str] = mapped_column(String(1024))
    caption: Mapped[str | None] = mapped_column(String(500))
    longitude: Mapped[float]
    latitude: Mapped[float]
    visibility: Mapped[Visibility] = mapped_column(Enum(Visibility), default=Visibility.private)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Friendship(Base):
    __tablename__ = "friendships"
    __table_args__ = (UniqueConstraint("requester_id", "addressee_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    addressee_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ImportJobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[ImportJobStatus] = mapped_column(Enum(ImportJobStatus), default=ImportJobStatus.pending)
    activities_seen: Mapped[int] = mapped_column(default=0)
    activities_imported: Mapped[int] = mapped_column(default=0)
    activities_with_new_coverage: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WebhookJobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    skipped = "skipped"
    failed = "failed"


class StravaWebhookJob(Base):
    __tablename__ = "strava_webhook_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_key: Mapped[str] = mapped_column(String(255), unique=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True)
    object_id: Mapped[int] = mapped_column(BigInteger, index=True)
    object_type: Mapped[str] = mapped_column(String(40))
    aspect_type: Mapped[str] = mapped_column(String(40))
    subscription_id: Mapped[int | None]
    event_time: Mapped[int | None]
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[WebhookJobStatus] = mapped_column(Enum(WebhookJobStatus), default=WebhookJobStatus.pending)
    attempts: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
