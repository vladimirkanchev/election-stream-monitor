Change area:
- HLS and `api_stream` loader behavior

Best first command:
- `just test-hls`

Why this lane fits:
- the change is in the stream-loading seam, not the whole runtime
- this lane covers playlist, fetch, progression, reconnect, and limits behavior without jumping straight to broader CI

When to run something broader:
- if the change also touched session orchestration, frontend bridge behavior, or CI-owned contract boundaries
- if the focused HLS lane passes but the branch still needs a push-readiness check

Next broader option:
- `just ci-local`
