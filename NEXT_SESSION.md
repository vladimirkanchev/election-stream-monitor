# Next Session

Use this file as the quick restart note if you come back after a break.

## Current Snapshot

- project stage: advanced prototype with a stable FastAPI-backed desktop
  runtime
- architecture shape: local-first modular monolith with explicit detector and
  alert-rule extension points
- main supported source modes:
  - `video_segments`
  - `video_files`
  - `api_stream` with direct `.m3u8` / `.mp4`
- FastAPI is the owned runtime backend for the main Electron session flow
- session service / CLI share the same backend session mechanics
- the HTTP/HLS loader is split into focused helper modules
- `src/main.py` is a legacy local developer harness, not a normal runtime path
- image mode was removed because it was not tested

## Good Re-Entry Points

If you want to get context back fast, read these in order:

1. [README.md](./README.md)
2. [docs/README.md](./docs/README.md)
3. [PLANS.md](./PLANS.md)

Then jump to the area you want:

- transport / HLS / playback:
  - [docs/contracts.md](./docs/contracts.md)
  - [docs/frontend-architecture.md](./docs/frontend-architecture.md)
  - [frontend/electron/hlsProxy.mjs](./frontend/electron/hlsProxy.mjs)
  - [src/stream_loader.py](./src/stream_loader.py)
- session lifecycle:
  - [docs/session-model.md](./docs/session-model.md)
  - [src/session_runner.py](./src/session_runner.py)
  - [src/session_models.py](./src/session_models.py)
- UI / playback UX:
  - [frontend/src/components/VideoPlayerPanel.tsx](./frontend/src/components/VideoPlayerPanel.tsx)
  - [frontend/src/components/SessionStatusPanel.tsx](./frontend/src/components/SessionStatusPanel.tsx)

## What Changed Recently

- remote HLS playback now goes through the local Electron HLS proxy
- `api_stream` got stricter source validation and clearer failure semantics
- the HTTP/HLS loader was split into focused playlist, fetch, materialize, and
  policy helpers
- `main.py` was demoted to a legacy local developer harness
- observability, trust policy, operator UX, and transport/session tests were
  expanded
- README, docs, and milestone notes were cleaned up for public-repo
  friendliness
- local image input support was removed

## Repo State To Remember

- the repo has some staged work plus unrelated local changes; check `git status`
  before committing anything new
- local runtime data under `data/` should stay local; do not clean your input
  video/stream folders by accident
- docs assets such as screenshots and architecture files live in
  [`docs/assets/`](./docs/assets/)

## Best Resume Commands

From the repo root:

```bash
. .venv/bin/activate
npm --prefix frontend run test
npm run build
npm run dev
```

If you need the full backend check again:

```bash
. .venv/bin/activate
pytest -q
```

## Best Next Steps

- review the current git state before the next commit
- if you continue code work, focus first on:
  - detector growth
  - `api_stream` hardening
  - FastAPI boundary polish
  - operator UX polish

## Do Not Forget

- YouTube / webpage player URLs are still unsupported
- some public HLS providers still block automated fetching even with the local
  proxy in place
- the project is ready for feedback, but still not fully pilot/production-ready
