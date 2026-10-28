# vhs-crt-look

A free Claude skill and command-line tool that applies the 1987 camcorder, VHS tape and CRT TV look from the short film **My Own Funeral** to anyone's images and videos. Plain Python 3.9+ with numpy and OpenCV, ffmpeg for video. No GPU, browser or network.

The skill itself is the [`vhs-crt-look/`](vhs-crt-look) folder: [`SKILL.md`](vhs-crt-look/SKILL.md) (what Claude follows), [`README.md`](vhs-crt-look/README.md) (for people), `scripts/` (the CLI and the `tapetube` package), `presets/looks.json` (every parameter), `LICENSE` (MIT).

## Layout

```
vhs-crt-look/                 the skill package (copy this folder to share or install)
  SKILL.md, README.md, LICENSE, requirements.txt
  presets/looks.json          tape V1-V7, tube C1-C5, treatments T0-T6, named looks, camera
  scripts/vhslook.py          CLI: doctor, looks, info, preview, render, compare, ladder, sheet, clip, page, rewind, params, selftest
  scripts/page-template.html  the offline comparison page
  scripts/tapetube/           sigproc, osd, vhs (tape chain), crt (tube), presets, media, pipeline, preview, page, rewind, selftest
tests/                        pytest suite
tools/fidelity_check.py       compares the tape chain with the film's own looktest.py (needs the film project and SciPy)
tools/package_skill.py        builds dist/vhs-crt-look-skill.zip
install.py                    installs the skill into ~/.claude/skills (or a project)
```

## Develop and test

```bash
python -m venv .venv && .venv/bin/python -m pip install -r vhs-crt-look/requirements.txt pytest ruff
.venv/bin/python -m pytest -q
.venv/bin/python vhs-crt-look/scripts/vhslook.py selftest --quick
.venv/bin/ruff check .
```

`VHSLOOK_SLOW=1 pytest` also runs the quick self-test from pytest. CI runs doctor, the unit tests and the full self-test on Linux (Python 3.9 and 3.13).

## Fidelity

`tools/fidelity_check.py <film project>` feeds identical frames to this tape chain and to the film's `looktest.py`. With seed 0 the final tape signal matches to within 6e-6 of full scale on all seven tape presets V1 to V7 (an 8-bit step is 3.9e-3). The tube is a numpy port of the film's three.js face shader (`comp/index_bd2.html`, look.json crt, tube and camera blocks).

## Quality gates

```bash
../scripts/quality-guardian.sh --repo-path . --check
bash ../scripts/design-quality-check.sh --repo-path .
```

## AI agent files

- `AGENTS.md`: project instructions for any agent
- `CLAUDE.md`: Claude Code extensions

---

Part of the [AI Projects Hub](https://github.com/arctidedev/AI).
