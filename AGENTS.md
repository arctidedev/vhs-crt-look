# AGENTS.md

Canonical instructions for any agent (Codex, Claude Code, others) working in this repository. Tool-agnostic. Claude Code's `CLAUDE.md` imports this file via `@AGENTS.md` and adds a small Claude-specific tail.

## Repository Expectations

- Project: `vhs-crt-look`
- Description: Free Claude Code skill: the 1987 camcorder, VHS tape and CRT TV look from My Own Funeral, for any image or video
- Stack: Python CLI Tool

## Commands

- Build/run: `uv run python -m vhs_crt_look`
- Test: `uv run pytest`
- Lint: `uv run ruff check .`

## Engineering Conventions

Python 3.13+, type hints everywhere, Pydantic v2 models, Click CLI, pathlib.Path, f-strings, snake_case functions, PascalCase classes

## Instrumentation Compliance (REQUIRED INFRASTRUCTURE)

This project was scaffolded with the Arctide instrumented baseline. The following are non-negotiable:

- **MetricKit** subscribed at app launch; payloads persist to `Documents/metrics/`.
- **OSLog** with subsystem = bundle ID and categories `app | network | data | ui` (see `Sources/Logger.swift`).
- **Sentry** initialized via xcconfig-injected `SENTRY_DSN` (no-op when empty).
- **TelemetryDeck** initialized via xcconfig-injected `TELEMETRYDECK_APP_ID` (no-op when empty).
- **Snapshot tests** target (`*SnapshotTests`) is a first-class part of CI/preflight.
- **Accessibility identifiers** on every interactive view, lint-enforced via `accessibility_identifier_required`. Add cases to `Sources/Instrumentation/AccessibilityIdentifiers.swift`.
- **Deep-link debug routing** for every screen (`Sources/Instrumentation/DebugRouter.swift`); URL scheme registered in `Info.plist`.
- **Typed analytics taxonomy** (`Sources/Telemetry/EventTaxonomy.swift`); never emit raw event names.
- **Privacy Manifest** (`Resources/PrivacyInfo.xcprivacy`) pre-populated; trim unused entries pre-submission, never empty.
- **Per-environment xcconfigs** (`xcconfigs/{Debug,Release,TestFlight,AppStore}.xcconfig`); drift checker fails on missing keys.

DO NOT bypass these for "simplicity" or "speed of feature work". Future agents that strip instrumentation should be reverted.

## Rules

- Run the narrowest relevant verification after changes, then broaden only if needed.
- Prefer existing project patterns over introducing a parallel architecture.
- Do not edit `*.sync-conflict-*` files unless the task is explicitly conflict resolution.
- Keep `README.md` and `AGENTS.md` aligned when shared commands or workflow rules change. Claude-specific extensions live in `CLAUDE.md` only.
- Check the parent AI hub for reusable scripts, hooks, and conventions before inventing new ones.
- Never commit secrets (`.env`, credentials, OAuth tokens, API keys).

## Cross-tool sync

This repo participates in the hub-wide cross-tool sync convention. When you start a session:

1. Read `.shared/cross-tool-log.md` if present — it shows what the other agent (Claude or Codex) recently changed in this project.
2. Codex auto-loads this `AGENTS.md` as base instructions; Claude Code reads it via `@AGENTS.md` import in `CLAUDE.md`.
3. The hub's PostToolUse hook appends to `.shared/cross-tool-log.md` automatically — don't write to it manually unless you know what you're doing (it's a ring-buffered file with locking).
4. **Never** enable Codex's review gate (`/codex:setup --enable-review-gate`) in this repo — it drains subscription quota.

## Session wrap-up

When the user says "wrap up", "wrap this session", or uses `/wrap-up`, run:

```
/Users/raulbrito/Projects/AI/scripts/session-wrapup.sh --repo "$(pwd)"
```

This commits all session work on a non-main branch, pushes it, opens or updates a PR, enables GitHub auto-merge, waits for the merge when possible, and after merge rebases eligible open worktrees onto the new `origin/main` with rollback checkpoints. Do not direct-push to `main`.

If the session was complex, noisy, or involved a lot of back and forth, the wrap-up script must add a `docs/session-wrapups/` note before committing. Use `--document` when in doubt.

## Parent Hub

This project belongs to the AI Projects Hub at `~/Projects/AI/`. Use the parent repo for meta-level changes; do project work from this child repository.
