# Hackathon NFL UNAM

A FastAPI backend and a React dashboard built on the NFL Big Data Bowl regional event data.

## Project layout

```
backend/     Python API (FastAPI)
dashboard/   Frontend (React + Vite + Tailwind)
data/        Event datasets
.hackathon/  Setup scripts and course tooling
.kiro/       Kiro steering and settings
```

## Requirements

- Python 3.12.12 (managed by `uv`)
- `uv` 0.11.19
- Node.js 22.23.1 with npm 10

The exact versions are listed in `.hackathon/stack.json`.

## Setup in a new environment

### Option A: course installer (recommended)

macOS / Linux:

```sh
sh .hackathon/setup.sh
```

Windows:

```bat
.hackathon\setup.cmd
```

The installer creates `.venv/` and installs the pinned Python packages and the Node tooling.

### Option B: manual setup

Python backend:

```sh
uv venv --python 3.12.12 .venv
uv pip install --python .venv -r .hackathon/requirements.txt
```

Dashboard:

```sh
cd dashboard
npm ci
```

## Running the project

Backend (API on port 8000):

```sh
.venv/bin/uvicorn backend.main:app --reload
```

Check it at `http://localhost:8000/health`.

Dashboard (development server):

```sh
cd dashboard
npm run dev
```

Build the dashboard for production:

```sh
cd dashboard
npm run build
```

## Credentials

Copy `.env.example` to `.env` and fill in the values. `.env` is ignored by git and must never be committed.

## Data

The event data is in `data/` and in `nfl-big-data-bowl-regional-event-data-main/data/`. See the data documentation in `nfl-big-data-bowl-regional-event-data-main/README.md` for the meaning of each file and its keys.
