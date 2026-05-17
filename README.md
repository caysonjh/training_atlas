# Atlas

Atlas is a private training map that turns Strava GPS history into sport-specific captured territory.

## Stack

- Next.js frontend, statically exported for Cloudflare Pages
- FastAPI backend, hosted as one Render free web service
- Supabase Postgres + PostGIS for durable spatial storage
- S3-compatible object storage for photo markers (Supabase Storage or Cloudflare R2 both fit)
- MapLibre for map rendering
- OpenFreeMap `positron` style by default for a quiet, route-first basemap

## Local setup

1. Copy `.env.example` to `.env` and fill in the Strava credentials.
2. Start local infrastructure:

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

4. Start the frontend:

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
6. Future Strava create webhooks are acknowledged immediately, persisted as jobs, then processed by the embedded backend worker loop.

## Free-first production stack

```text
Cloudflare Pages  -> static frontend
Render free web   -> FastAPI API + embedded webhook worker
Supabase          -> Postgres + PostGIS
Object storage    -> Supabase Storage or Cloudflare R2
```

This keeps the long-lived atlas data out of Render's expiring free Postgres tier while preserving a zero-cost path for the personal app.

## Supabase setup

1. Create a Supabase project.
2. In Database -> Extensions, enable `postgis`.
3. Copy the direct Postgres connection string into the Render backend as `DATABASE_URL`.
4. Use these Render backend values for Supabase-backed PostGIS:

   ```env
   DB_SEARCH_PATH=public,extensions
   BOOTSTRAP_POSTGIS_EXTENSION=false
   ```

If you use Supabase Storage for photos, enable its S3 protocol and set the backend `S3_*` env vars from the storage credentials. Cloudflare R2 also works because it is S3-compatible.

## Render backend setup

Create one Render Web Service from this repository:

- Root directory: `backend`
- Build command: `pip install -e .`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

`render.yaml` now describes only that free backend service. Set these env vars in Render:

```env
DATABASE_URL=
STRAVA_CLIENT_ID=
STRAVA_CLIENT_SECRET=
STRAVA_VERIFY_TOKEN=
STRAVA_WEBHOOK_SECRET=
FRONTEND_URL=
BACKEND_URL=
S3_ENDPOINT_URL=
S3_ACCESS_KEY=
S3_SECRET_KEY=
S3_BUCKET=
S3_PUBLIC_BASE_URL=
DB_SEARCH_PATH=public,extensions
BOOTSTRAP_POSTGIS_EXTENSION=false
EMBEDDED_WEBHOOK_WORKER=true
WEBHOOK_WORKER_POLL_SECONDS=5
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=none
```

The last two cookie settings are required because the Cloudflare Pages frontend and Render backend use different domains in production.

## Cloudflare Pages frontend setup

Create one Pages project from this repository:

- Root directory: `frontend`
- Build command: `npm run build`
- Build output directory: `out`

Set these build-time env vars in Cloudflare Pages:

```env
NEXT_PUBLIC_API_URL=https://YOUR-RENDER-BACKEND
NEXT_PUBLIC_MAP_STYLE_URL=https://tiles.openfreemap.org/styles/positron
```

## Migrating the current local atlas

Run this after Supabase exists and before treating production as canonical:

```bash
LOCAL_DATABASE_URL='postgresql+psycopg://...' \
PRODUCTION_DATABASE_URL='postgresql://...' \
./scripts/migrate_postgres.sh atlas-local.dump
```

Then verify the copy:

```bash
LOCAL_DATABASE_URL='postgresql+psycopg://...' \
PRODUCTION_DATABASE_URL='postgresql://...' \
python scripts/verify_migration.py
```


## Strava production setup

1. In your Strava API app settings, change the callback domain from `localhost` to the Render backend domain.
2. Register the live webhook after the backend is deployed:

   ```bash
   cd backend
   python scripts/strava_subscription.py refresh --callback-url https://YOUR-RENDER-BACKEND/webhooks/strava
   ```

## Notes

- V1 maps exact traveled GPS paths rather than official road segments.
- Repeated routes do not visually thicken the atlas.
- Pool swims are ignored; only GPS-bearing open-water swims are mapped.
- Photo markers are uploaded manually in v1.
- Follow-on roadmap candidates: per-sport unique distance, friend overlays, and broader summary metrics.
