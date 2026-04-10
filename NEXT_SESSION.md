# Next Session

Use this file as the quick restart note if you come back after a break.

## Current Snapshot

- project stage: advanced prototype moving toward pre-pilot
- architecture shape: local-first modular monolith with plugin-style extension
  points around detectors and alert rules
- main supported source modes:
  - `video_segments`
  - `video_files`
  - `api_stream` with direct `.m3u8` / `.mp4`
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
- observability, trust policy, operator UX, and transport/session tests were
  expanded
- README and docs were cleaned up for public-repo friendliness
- local image input support was removed

## Repo State To Remember

- the repo is still in a heavy pre-commit / first-baseline state with many
  staged files
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

- review the current git state before the first public push
- decide what should be included from `docs/assets/`
- if you continue code work, focus first on:
  - detector growth
  - `api_stream` hardening
  - FastAPI boundary preparation
  - operator UX polish

## Do Not Forget

- YouTube / webpage player URLs are still unsupported
- some public HLS providers still block automated fetching even with the local
  proxy in place
- the project is ready for feedback, but still not fully pilot/production-ready
