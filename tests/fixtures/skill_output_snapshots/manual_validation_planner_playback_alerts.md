Validation target:
- desktop playback and alert-rendering flow after a UI/backend change

Best local flow:
- run the normal Electron app
- start one local session that reaches progress updates and visible alerts

What to click/run:
- start the app with `npm run dev`
- start a local monitoring session from the desktop UI
- open the session details or status panel
- trigger or use a fixture path where playback progress and alert entries should appear

What to watch for:
- the session leaves idle and shows active progress
- playback or status text updates without falling back incorrectly
- alert or incident entries appear in the expected panel

Failure signal:
- UI falls back to idle while the backend session is still active
- playback state stalls or flickers incorrectly
- expected alerts never appear or render in the wrong place

Best follow-up automation:
- run `just test-frontend` if the issue looks bridge or UI-owned
- run `just test-alert-rules` if the issue looks policy-owned
- run `just test-fast` or `just ci-local` only if the focused lane is not enough
