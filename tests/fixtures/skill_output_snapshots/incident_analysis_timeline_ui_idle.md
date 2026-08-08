Observed facts:
The session start request succeeded, but the UI later returned to an idle-looking state.

Reconstructed sequence:
The frontend requested session start, the backend accepted it, the detached worker began startup, and the frontend did not get a stable first persisted snapshot quickly enough to keep its active state.

Trigger:
Operator clicked Start Monitoring for a valid source.

First visible symptom:
The interface stopped behaving like an active monitoring run and appeared to fall back to idle.

Backend events:
Session start was accepted, the worker process was launched, and session persistence lag or failure became relevant before the first stable read.

Frontend events:
The frontend started monitoring, attempted to read the session snapshot, and then had to interpret the early read outcome.

Persistence/session-file events:
The first `session.json` or related snapshot files were either not yet visible or not yet readable when the frontend performed its early follow-up read.

Terminal state:
The operator-visible state became inconsistent with the earlier accepted start request.

Unknowns still left:
Whether the issue was only transient startup lag or a real worker/persistence failure.
