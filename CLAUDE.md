@AGENTS.md

# Claude Code-specific extensions for vhs-crt-look

Canonical project rules live in `AGENTS.md` (imported above). This file adds Claude Code-specific extensions only.

## Slash commands available in this project

- `/triad <task>` — Architect → Executor → Reviewer (Reviewer phase uses Codex by default; pass `--no-codex` to force Claude-only).
- `/codex-implement <plan-file>` — Claude plans, Codex executes the plan, Claude reviews the diff.
- `/codex:adversarial-review` / `/codex:review` — manual Codex review of working-tree or branch diff.

## Token optimization (Claude-specific)

- `/clear` between unrelated tasks.
- `/compact` near 70% context. PreCompact saves a snapshot; PostCompact re-injects it (which now also includes the cross-tool sync digest so Codex awareness survives the compaction).
- Delegate verbose generation to subagents — `SubagentStart` hook auto-injects hub context.
- Skills loaded on-demand — never paste large reference docs into conversation.

## Hub references

- Parent CLAUDE.md: `~/Projects/AI/CLAUDE.md` (hub-wide Claude extensions).
- Cross-tool log: `.shared/cross-tool-log.md` (gitignored; auto-updated by hub PostToolUse hook).
- Health check: `bash ~/Projects/AI/scripts/health-cross-sync.sh`.
- Design quality: load the `design-quality` skill for UI work, use the session's Opus model at `max` effort for taste-sensitive direction (subagents and workflows omit `model` to inherit it; never `fable`/`best` unless Raul explicitly asks, since Fable has a separate weekly limit) — then run `bash ../scripts/design-quality-check.sh --repo-path .`.

## Instrumentation

Not applicable here (Python CLI skill, no app target); see AGENTS.md. The comparison page's interactive elements carry `data-testid`.
