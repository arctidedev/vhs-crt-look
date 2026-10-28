# AGENTS.md

Canonical instructions for any agent (Codex, Claude Code, others) working in this repository. Tool-agnostic. Claude Code's `CLAUDE.md` imports this file via `@AGENTS.md` and adds a small Claude-specific tail.

## Repository Expectations

- Project: `vhs-crt-look`
- Description: Free Claude Code skill: the 1987 camcorder, VHS tape and CRT TV look from My Own Funeral, for any image or video
- Stack: Python CLI Tool

## Commands

- Run: `python vhs-crt-look/scripts/vhslook.py <command>` (doctor, looks, info, preview, render, compare, ladder, sheet, clip, page, rewind, params, selftest)
- Test: `python -m pytest -q` and `python vhs-crt-look/scripts/vhslook.py selftest --quick`
- Lint: `ruff check .`
- Fidelity against the film: `python3 tools/fidelity_check.py <film project dir>` (needs SciPy and the film project, read-only)
- Package: `python tools/package_skill.py` (dist/vhs-crt-look-skill.zip); install: `python install.py`

## Engineering Conventions

- The skill package is `vhs-crt-look/`; it must stay self-contained and portable: Python 3.9+, numpy and opencv-python-headless only (no SciPy, no PIL), ffmpeg/ffprobe through subprocess for video. Paths via os.path, binary pipes, `if __name__ == "__main__"` guards (Windows spawns worker processes).
- The tape chain (`tapetube/vhs.py`) is a line-for-line port of the film's `looktest.py`; keep it numerically faithful (run the fidelity check after touching it). Parameter names match the film's (`presets/looks.json`).
- Deterministic: per-frame random streams from (seed, frame index), never from worker order.
- Video streams frame by frame; never hold a whole clip in memory.
- Copy (SKILL.md, README, labels, page): neutral technical wording, no em dashes.

## Instrumentation

The arctide iOS instrumentation baseline does not apply (no app target). The only UI is the offline comparison page (`vhs-crt-look/scripts/page-template.html`): every interactive element carries a `data-testid`, design notes live in `DESIGN.md`.

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
