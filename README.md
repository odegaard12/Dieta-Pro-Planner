# Diet Pro Planner

**Current version:** v0.0.11

Local-first web app for tracking body weight, meals by grams, reusable foods, meal templates, workouts, weekly plans and optional integrations.

Designed to run privately on a Raspberry Pi with Docker. Your personal data stays local.

## Features

- Official and reference weight tracking.
- Meal logging by saved foods and grams.
- Reusable meal templates where you can adjust quantities before saving.
- Product catalog with brand, nutrition values and optional local label photo.
- Local OCR helper for food labels using Tesseract.
- OCR3 parser with validation, cache and known-label correction for common products.
- Manual workout logging.
- Strava OAuth connection through localhost.
- Manual Strava import by date range.
- Optional Strava auto-sync in the Raspberry background.
- Strava calories are read from detailed activity data when available.
- UI5 blue responsive layout with redesigned sidebar, topbar, dashboard cards and daily rule cards.
- Sport dashboard with 7-day summary and compact workout cards.
- Editable weekly plan board with horizontal day cards.
- Local SQLite database in `data/dieta.db`.

## Privacy

Do not commit local or private files. The repository excludes them through `.gitignore`:

- `data/`
- `uploads/`
- `*.db`
- `*.sqlite`
- `.env`
- tokens
- backups
- ZIP files
- local label photos
- OCR cache files

## Docker

```bash
docker compose up -d --build
```

Default local URL:

```text
http://localhost:8099
```

## Strava local setup

Diet Pro Planner can connect to Strava without exposing the Raspberry Pi to the internet.

Recommended local OAuth flow:

1. Create a Strava API application.
2. Set the website to `http://localhost:8099`.
3. Set the authorization callback domain to `localhost`.
4. Store `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET` and `STRAVA_REDIRECT_URI` in the local `.env` file.
5. Open an SSH tunnel from your computer to the Raspberry Pi:

```bash
ssh -N -L 8099:127.0.0.1:8099 user@raspberry-ip
```

6. Open `http://localhost:8099`.
7. Go to Integrations -> Strava -> Connect Strava.

Tokens are stored locally under `data/` and are excluded from Git.

## Strava import modes

- Manual preview by date range.
- Select activities before importing.
- Duplicate protection by Strava activity id.
- Optional auto-sync in the Raspberry background.
- Auto-sync imports newly detected activities every configured interval.
- A visible status message shows the latest successful sync time.

## OCR food labels

Food-label OCR is local-first:

- photos stay local,
- OCR results are editable before saving,
- impossible nutrition values are discarded,
- repeated image reads can use local OCR cache.

## Releases

- `v0.0.1`: first clean public release.
- `v0.0.2`: manual Strava import by date range.
- `v0.0.3`: branding, app icon, ES/EN toggle and Strava auto-preview.
- `v0.0.4`: background Strava auto-sync and last-sync status.
- `v0.0.5`: safe UI translation cleanup.
- `v0.0.6`: stable Spanish UI after removing broken translation layer.
- `v0.0.7`: UTF-8 cleanup and Strava detailed-activity calorie import.
- `v0.0.8`: sidebar daily-rule visibility fix.
- `v0.0.9`: curated products, practical templates and improved assistant.
- `v0.0.10`: improved weight system and compact food-label helper.
- `v0.0.11`: UI5 redesign, OCR3 label parser, sport dashboard and editable weekly plan.

## Notes

This repository contains only the public application code. Local user data, databases, environment files, Strava tokens, backups, OCR cache files and uploaded label photos must remain private.
