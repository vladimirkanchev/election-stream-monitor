Current base version:
- `0.5.2`

Change class:
- larger-than-patch persistence rollout work with real milestone intent, but still partly opt-in rather than fully default runtime behavior

Recommended version:
- keep the branch framed below `0.6.0` until the supported runtime story is complete

Why not smaller:
- the work is more than a narrow fix because it changes backend selection, persistence confidence, and milestone framing

Why not larger:
- the default runtime path is still file-backed, so the branch does not yet read like a finished persistence milestone

What must be true first:
- code, tests, and owning docs must all support the same PostgreSQL-backed milestone claim
- the version story should describe one coherent release outcome rather than partial migration progress
