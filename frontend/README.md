# Kpinder Frontend

React + TypeScript + Vite frontend for Kpinder. See the [repo root README](../README.md) for the full local setup (Docker DB + backend); this file covers frontend-only commands.

## Setup

```sh
cp .env.example .env   # API_URL (defaults to http://localhost:8000)
npm install
```

## Run

```sh
npm run dev
```

Serves on `http://localhost:5173`. Requires the backend running at `API_URL` (see [`backend/README.md`](../backend/README.md)).

## Lint, format, build

```sh
npm run lint     # eslint + prettier --check
npm run format   # prettier --write
npm run build    # tsc -b && vite build
```
