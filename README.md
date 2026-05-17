# Atlas

Atlas is a private training map that turns Strava GPS history into sport-specific captured territory.

## Stack

- Next.js frontend
- FastAPI backend
- PostgreSQL + PostGIS
- MinIO-compatible object storage for photo markers
- MapLibre for map rendering
- OpenFreeMap `positron` style by default for a quiet, route-first basemap

## Local setup

1. Copy `.env.example` to `.env` and fill in the Strava credentials.
2. Start infrastructure:

   ```bash
   docker compose up -d db minio
   ```

3. Start the backend:

   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   uvicorn app.main:app --reload --port 8000
   ```

4. Start the webhook worker in a second backend terminal:

   ```bash
   cd backend
   source .venv/bin/activate
   python -m app.worker
   ```

5. Start the frontend:

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

Open `http://localhost:3000`.

## Core flow

1. Connect Strava from the atlas UI.
2. Atlas exchanges the OAuth code for tokens and stores the athlete connection.
3. Import history fetches historical activities and GPS streams.
4. Each valid GPS line is compared against previously captured territory for the same user and sport.
5. Only newly covered geometry is stored and rendered.
6. Future Strava create webhooks are acknowledged immediately, persisted as jobs, then processed by the worker.

## Render deployment

`render.yaml` defines four resources: the FastAPI web service, a dedicated webhook worker, the Next.js web service, and PostgreSQL. Render Postgres supports PostGIS; after creating the database, enable it once with `CREATE EXTENSION IF NOT EXISTS postgis;` if the restored database has not already done so.

Set the secret env vars in Render before the first live deploy:

- `STRAVA_CLIENT_ID`
- `STRAVA_CLIENT_SECRET`
- `STRAVA_VERIFY_TOKEN`
- `STRAVA_WEBHOOK_SECRET` if you enable signed webhook verification
- `FRONTEND_URL`
- `BACKEND_URL`
- the S3-compatible storage settings
- frontend `NEXT_PUBLIC_API_URL`

Once both public services are live, update the Strava app callback domain to the hosted backend domain and refresh the single Strava webhook subscription:

```bash
cd backend
python scripts/strava_subscription.py list
python scripts/strava_subscription.py refresh --callback-url https://YOUR-BACKEND/webhooks/strava
```

## Migrating the current local atlas

Run this only after the production database exists and before treating production as canonical:

```bash
LOCAL_DATABASE_URL='postgresql+psycopg://...' \
PRODUCTION_DATABASE_URL='postgresql://...' \
./scripts/migrate_local_to_render.sh atlas-local.dump
```

That copies users, Strava credentials, activities, tracks, captured geometry, photos, import history, and webhook jobs as a single PostgreSQL restore so the hosted atlas begins with the same terrain already visible locally. Verify the copy before cutover:

```bash
LOCAL_DATABASE_URL='postgresql+psycopg://...' \
PRODUCTION_DATABASE_URL='postgresql://...' \
python scripts/verify_migration.py
```

## Notes

- V1 maps exact traveled GPS paths rather than official road segments.
- Repeated routes do not visually thicken the atlas.
- Pool swims are ignored; only GPS-bearing open-water swims are mapped.
- Photo markers are uploaded manually in v1.
- Follow-on roadmap candidates: per-sport unique distance, friend overlays, and broader summary metrics.
