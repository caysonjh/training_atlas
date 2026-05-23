# Atlas

Atlas is a local-first private training map. It connects to Strava, stores your activities in your own local Postgres/PostGIS database, and renders the unique roads/trails/water you have covered by sport.

The hosted Render/Supabase path is no longer the primary workflow. For this personal atlas, the reliable path is:

```text
Browser UI on localhost:3000
        ↓
FastAPI on localhost:8000
        ↓
Local Postgres + PostGIS
```

## What works in the local-first app

- Strava OAuth through the normal Strava API. Do not enter Strava username/password into Atlas.
- One-click **Sync Strava** from the UI.
- First sync imports your available Strava GPS history.
- Later syncs are incremental: Atlas asks Strava only for activities after your newest saved activity, with a small overlap window to avoid missing recent edits.
- Existing activities are skipped, so repeated syncs should be fast and idempotent.
- Webhooks are optional and not needed for the local-first workflow.

## Requirements

- Docker Desktop, for local Postgres/PostGIS
- Python 3.11+
- Node.js 18+
- A Strava API app

In Strava API settings, set the callback domain to:

```text
localhost
```

## Setup

1. Copy the environment template:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and set:

   ```env
   STRAVA_CLIENT_ID=your_client_id
   STRAVA_CLIENT_SECRET=your_client_secret
   BACKEND_URL=http://localhost:8000
   FRONTEND_URL=http://localhost:3000
   ```

3. Start the app:

   ```bash
   ./scripts/start_app.sh
   ```

4. Open:

   ```text
   http://localhost:3000
   ```

5. Click **Connect Strava**, approve access, then click **Sync Strava**.

## Manual startup

If you do not want to use the launcher script:

```bash
docker compose up -d db

cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

## Sync behavior

The main endpoint is:

```text
POST /sync/strava
```

By default it performs an incremental sync:

1. Find the newest saved Strava activity in the local database.
2. Ask Strava for activities after that date minus `STRAVA_SYNC_OVERLAP_DAYS`.
3. Skip activities already saved locally.
4. Fetch GPS streams only for new supported activities.
5. Store only newly captured geometry.

For repair/backfill work, the old full-history endpoint still exists:

```text
POST /imports/strava/history
```

It is intentionally not the primary UI action anymore.

## Photo storage

Photo uploads are saved locally under `backend/data/photos/` and served by FastAPI at `/media/photos/...`. MinIO/S3 settings are legacy and are not required for the local-first workflow.

## Environment knobs

Useful local settings in `.env`:

```env
DATABASE_URL=postgresql+psycopg://atlas:atlas@localhost:5432/atlas
DB_SEARCH_PATH=public
BOOTSTRAP_POSTGIS_EXTENSION=true
CREATE_TABLES_ON_STARTUP=true
RECOVER_JOBS_ON_STARTUP=true
EMBEDDED_WEBHOOK_WORKER=false
STRAVA_IMPORT_PAGE_SIZE=30
STRAVA_SYNC_OVERLAP_DAYS=7
STRAVA_FULL_IMPORT_EXISTING_STOP_AFTER=30
SESSION_COOKIE_SECURE=false
SESSION_COOKIE_SAMESITE=lax
```

## Notes

- Atlas maps exact traveled GPS paths rather than official road segments.
- Repeated routes do not visually thicken the atlas.
- Pool swims are ignored; only GPS-bearing open-water swims are mapped.
- Photo markers are uploaded manually and stored under `backend/data/photos/` in the local-first app.
- Future hosted deployment can still be revisited later, but local-first removes the Render memory and Supabase pooler failure modes from daily use.
