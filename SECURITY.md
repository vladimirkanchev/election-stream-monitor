# Security Notes

Election Stream Monitor is currently a local-first advanced prototype moving
toward pre-pilot.

## Reporting Security Concerns

If you find a security issue, please avoid posting sensitive exploit details in
a public issue before maintainers have had a chance to assess it.

For now, prefer a private disclosure route with the repo owner/maintainer if
one is available.

## Current Security Posture

The project already applies a few important trust boundaries:

- `api_stream` input validation only accepts direct `.m3u8` and `.mp4` URLs
- webpage-style player URLs are rejected early
- credentialed URLs are rejected
- private and loopback hosts are rejected by default
- service-mode fetching is intended to run behind an explicit allowlist

## Important Limits

This is not yet a hardened multi-tenant service.

Known limits:

- remote provider behavior is still being hardened
- broader service-mode deployment needs more auth, observability, and
  operational controls
- GitHub Actions CI is a correctness check, not a security review

## Related Docs

- [docs/contracts.md](./docs/contracts.md)
- [docs/fastapi-boundary.md](./docs/fastapi-boundary.md)
- [docs/testing-and-validation.md](./docs/testing-and-validation.md)
