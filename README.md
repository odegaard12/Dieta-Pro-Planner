# Diet Pro Planner

**Current version:** v0.0.1

Local-first web app for tracking body weight, meals by grams, reusable foods, meal templates, workouts, weekly plans and optional integrations.

Designed to run privately on a Raspberry Pi with Docker. Your personal data stays local.

## Features

- Official and reference weight tracking.
- Meal logging by saved foods and grams.
- Reusable meal templates where you can adjust quantities before saving.
- Product catalog with brand, nutrition values and optional local label photo.
- Manual workout logging.
- Strava integration scaffold for future manual sync.
- Local SQLite database in data/dieta.db.

## Privacy

Do not commit local or private files. The repository excludes them through .gitignore:

- data/
- *.db
- *.sqlite
- .env
- tokens
- backups
- ZIP files
- local label photos

## Docker

Run locally with Docker Compose:

docker compose up -d --build

Default local URL:

http://localhost:8099

## Docker image

ghcr.io/odegaard12/diet-pro-planner:0.0.1

## Releases

- v0.0.1: first clean public release.
