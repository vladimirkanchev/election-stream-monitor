# Changelog

All notable changes to this project should be documented in this file.

The format is intentionally lightweight and practical for the current project
stage.

## [Unreleased]

- ongoing transport, session, and operational hardening
- continued frontend/operator UX refinement

## [0.3.1] - 2026-05-18

CI/CD hardening and test-coverage follow-up release.

Highlights:

- stronger CI ownership and drift guards for workflow targets, path existence,
  split-suite registration, and frontend contract targeting
- short CI maintainer guide plus tighter CI/project doc alignment
- expanded and refactored focused CI-helper regression coverage
- alert-query slice cleanup with tighter typing and direct adapter seam tests

## [0.3.0] - 2026-05-09

FastAPI boundary and MCP feature update.

Highlights:

- local MCP server with read-only alert-query tools
- grouped alert timeline and incident-summary query tools
- explicit FastAPI `local` and `share` access modes
- API-key auth and rate limiting for temporary shared demo access
- split and expanded boundary-focused test coverage

## [0.1.0] - 2026-04-06

Initial public baseline prepared for repository sharing.

Highlights:

- local-first monitoring workflow across frontend, Electron bridge, and Python
  backend
- direct `api_stream` support for remote `.m3u8` and `.mp4` inputs
- local Electron HLS proxy for remote HLS playback
- explicit trust policy for remote media fetching
- documented architecture, contracts, reviewer guide, testing notes, and
  FastAPI boundary
- backend and frontend test coverage plus lightweight CI workflow
