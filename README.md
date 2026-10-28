# vhs-crt-look

Free Claude Code skill: the 1987 camcorder, VHS tape and CRT TV look from My Own Funeral, for any image or video

## Getting Started

```bash
uv run python -m vhs_crt_look
```

## Testing

```bash
uv run pytest
```

## Quality Gates

```bash
../scripts/quality-guardian.sh --repo-path . --check
../scripts/quality-guardian.sh --repo-path . --fix
```

## AI Agent Files

- `AGENTS.md` — Codex/project instructions
- `CLAUDE.md` — Claude Code instructions

Start isolated Codex sessions from this repo with:

```bash
../scripts/codex-worktree-session.sh --repo . --slug <task>
```

## Tech Stack

Python CLI Tool

---

Part of the [AI Projects Hub](https://github.com/arctidedev/AI).
