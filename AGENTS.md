# AGENTS.md

Instructions for coding agents (Claude Code, Codex and others) working in this repository.

## What this is

A Claude skill and command-line tool that gives photos and videos a 1987 camcorder, VHS tape and CRT TV look. The skill is the `vhs-crt-look/` folder; `README.md` is for people installing and using it, `DEVELOPMENT.md` for developers.

## Commands

- Run: `python vhs-crt-look/scripts/vhslook.py <command>` (setup, doctor, looks, info, preview, render, compare, ladder, sheet, clip, page, rewind, params, selftest)
- Test: `python -m pytest -q` and `python vhs-crt-look/scripts/vhslook.py selftest --quick`
- Lint: `ruff check .` and `ruff format --check .`; types: `pyright`
- Package: `python tools/package_skill.py` (dist/vhs-crt-look-skill.zip)

## Conventions

- The skill folder must stay self-contained and portable: Python 3.9+, numpy and opencv-python-headless only (no SciPy, no PIL), ffmpeg and ffprobe through subprocess for video. `scripts/setup_env.py` and `tapetube/ffbin.py` use the standard library only.
- The tape chain (`tapetube/vhs.py`) is a line-for-line port of the reference look-development code; keep it numerically faithful. Parameter names match `presets/looks.json`.
- Deterministic: per-frame random streams come from (seed, frame index), never from worker order.
- Video streams frame by frame; never hold a whole clip in memory.
- Windows: `Install on Windows.bat` keeps CRLF line endings (`.gitattributes`); worker processes need `if __name__ == "__main__"` guards.
- Copy (README, SKILL.md, labels, the comparison page): plain, neutral wording, no em dashes.
- The comparison page's interactive elements carry `data-testid`; design notes are in `DESIGN.md`.
- Never commit secrets.
