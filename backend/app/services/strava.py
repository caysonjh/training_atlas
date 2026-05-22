from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Activity, ActivityType, StravaConnection, User

SPORT_MAP = {
    "Ride": ActivityType.road_cycling,
    "MountainBikeRide": ActivityType.mountain_biking,
    "GravelRide": ActivityType.gravel_biking,
    "Run": ActivityType.running,
    "TrailRun": ActivityType.trail_running,
    "Swim": ActivityType.open_water_swimming,
}


def oauth_url() -> str:
    return (
        "https://www.strava.com/oauth/authorize"
        f"?client_id={settings.strava_client_id}"
        f"&redirect_uri={settings.backend_url}/auth/strava/callback"
        "&response_type=code"
        "&approval_prompt=auto"
        "&scope=read,activity:read_all"
    )


async def exchange_code(code: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://www.strava.com/oauth/token",
            data={
                "client_id": settings.strava_client_id,
                "client_secret": settings.strava_client_secret,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        return response.json()


async def refresh_access_token(connection: StravaConnection) -> None:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://www.strava.com/oauth/token",
            data={
                "client_id": settings.strava_client_id,
                "client_secret": settings.strava_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": connection.refresh_token,
            },
        )
        response.raise_for_status()
        payload = response.json()
        connection.access_token = payload["access_token"]
        connection.refresh_token = payload["refresh_token"]
        connection.expires_at = payload["expires_at"]


def upsert_user_and_connection(db: Session, payload: dict) -> User:
    athlete = payload["athlete"]
    user = db.scalar(select(User).where(User.strava_athlete_id == athlete["id"]))
    if not user:
        user = User(
            strava_athlete_id=athlete["id"],
            display_name=f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip() or "Athlete",
            avatar_url=athlete.get("profile"),
        )
        db.add(user)
        db.flush()
    connection = db.get(StravaConnection, user.id)
    if not connection:
        connection = StravaConnection(user_id=user.id, access_token="", refresh_token="", expires_at=0, scope="")
        db.add(connection)
    connection.access_token = payload["access_token"]
    connection.refresh_token = payload["refresh_token"]
    connection.expires_at = payload["expires_at"]
    connection.scope = payload.get("scope", "")
    db.commit()
    return user


async def get_authenticated_connection(db: Session, user: User) -> StravaConnection:
    connection = db.get(StravaConnection, user.id)
    if not connection:
        raise ValueError("No Strava connection")
    if connection.expires_at <= int(datetime.now(timezone.utc).timestamp()) + 60:
        await refresh_access_token(connection)
        db.commit()
    return connection


async def iter_activity_pages(connection: StravaConnection, per_page: int = 100, after: int | None = None):
    page = 1
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            params = {"per_page": per_page, "page": page}
            if after is not None:
                params["after"] = after
            response = await client.get(
                "https://www.strava.com/api/v3/athlete/activities",
                headers={"Authorization": f"Bearer {connection.access_token}"},
                params=params,
            )
            response.raise_for_status()
            batch = response.json()
            if not batch:
                return
            yield batch
            if len(batch) < per_page:
                return
            page += 1


async def fetch_activities(connection: StravaConnection) -> list[dict]:
    activities: list[dict] = []
    async for batch in iter_activity_pages(connection):
        activities.extend(batch)
    return activities


async def fetch_activity(connection: StravaConnection, activity_id: int) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"https://www.strava.com/api/v3/activities/{activity_id}",
            headers={"Authorization": f"Bearer {connection.access_token}"},
        )
        response.raise_for_status()
        return response.json()


async def fetch_latlng_stream(connection: StravaConnection, activity_id: int) -> list[list[float]]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"https://www.strava.com/api/v3/activities/{activity_id}/streams",
            headers={"Authorization": f"Bearer {connection.access_token}"},
            params={"keys": "latlng", "key_by_type": "true"},
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("latlng", {}).get("data", [])


def atlas_type_for(activity_payload: dict) -> ActivityType | None:
    sport_type = activity_payload.get("sport_type") or activity_payload.get("type")
    atlas_type = SPORT_MAP.get(sport_type)
    if atlas_type == ActivityType.open_water_swimming and not activity_payload.get("start_latlng"):
        return None
    return atlas_type


def activity_from_payload(user_id: int, payload: dict) -> Activity:
    return Activity(
        user_id=user_id,
        strava_activity_id=payload["id"],
        name=payload.get("name") or "Untitled activity",
        sport_type=payload.get("sport_type") or payload.get("type") or "Unknown",
        atlas_type=atlas_type_for(payload),
        started_at=datetime.fromisoformat(payload["start_date"].replace("Z", "+00:00")),
        is_private=payload.get("private", False),
        has_gps=bool(payload.get("start_latlng")),
    )

