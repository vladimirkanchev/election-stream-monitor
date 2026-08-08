Security surface:
- FastAPI alerts HTTP routes exposed through local `share` mode

Current protection:
- API-key auth and rate limiting are enabled in `share` mode
- MCP remains a separate local `stdio` surface rather than sharing the same HTTP exposure path

Main risk:
- contributors may over-assume that all local runtime surfaces are equally protected when only certain HTTP routes are covered

Best next hardening step:
- keep the boundary description explicit in code and docs
- review whether newly exposed routes belong inside the same auth and rate-limit policy

What is intentionally out of scope:
- full remote multi-user security posture
- hosted-service style hardening beyond the current local/demo stage
