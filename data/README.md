# Local Data Policy

The `data/` tree is for local runtime artifacts and developer-owned sample
inputs.

Do not commit generated session outputs, downloaded streams, or local metrics
from everyday runs. In practice that means these paths stay ignored:

- `data/sessions/`
- `data/streams/`
- `data/metrics/`
- `data/video_files/`

Use `tests/fixtures/` for deterministic test assets that must live in the repo.

If you need to document a sample source, prefer a short note in `docs/` or
`README.md` instead of checking in live session output.
