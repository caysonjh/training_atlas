from datetime import datetime

from pydantic import BaseModel, Field

from .models import ActivityType, ImportJobStatus


class ActivityOut(BaseModel):
    id: int
    name: str
    sport_type: str
    atlas_type: ActivityType | None
    started_at: datetime

    model_config = {"from_attributes": True}


class PhotoOut(BaseModel):
    id: int
    image_url: str
    caption: str | None
    longitude: float
    latitude: float

    model_config = {"from_attributes": True}


class PhotoCreate(BaseModel):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    caption: str | None = Field(default=None, max_length=500)
    activity_id: int | None = None


class PhotoUpdate(BaseModel):
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    caption: str | None = Field(default=None, max_length=500)


class ImportJobOut(BaseModel):
    id: int
    status: ImportJobStatus
    activities_seen: int
    activities_imported: int
    activities_with_new_coverage: int
    error: str | None

    model_config = {"from_attributes": True}


class StravaStatusOut(BaseModel):
    connected: bool
    athlete_name: str | None = None
    athlete_id: int | None = None


class MapStatsOut(BaseModel):
    total_unique_distance_meters: float
