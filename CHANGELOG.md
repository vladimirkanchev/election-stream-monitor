# Changelog

All notable changes to this project should be documented in this file.

The format is intentionally lightweight and practical for the current project
stage.

## [Unreleased]

- ongoing transport, session, and operational hardening
- continued frontend/operator UX refinement
- preparation for clearer FastAPI-backed local deployment

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
