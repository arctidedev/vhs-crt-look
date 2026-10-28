# Development

The skill is the [`vhs-crt-look/`](vhs-crt-look) folder: [`SKILL.md`](vhs-crt-look/SKILL.md) (what Claude follows), [`README.md`](vhs-crt-look/README.md) (what people see after unzipping), the installers, `scripts/` (the CLI, `setup_env.py` and the `tapetube` package), `presets/looks.json` (every parameter) and `LICENSE` (MIT). Plain Python 3.9+ with numpy and OpenCV, ffmpeg for video. No GPU, browser or network.

## Layout

```
vhs-crt-look/                     the skill package (this folder is what the zip contains)
  SKILL.md, README.md, LICENSE, requirements.txt
  Install on Mac.command          double-click installer (runs install.sh)
  Install on Windows.bat          double-click installer (CRLF line endings, see .gitattributes)
  install.sh                      macOS and Linux installer: copy to ~/.claude/skills, then `vhslook.py setup`
  presets/looks.json              tape V1-V7, tube C1-C5, treatments T0-T6, named looks, camera
  scripts/vhslook.py              CLI: setup, doctor, looks, info, preview, render, compare, ladder, sheet, clip, page,
                                  rewind, params, selftest; switches to the skill's own .venv when it exists
  scripts/setup_env.py            one-time setup, standard library only
  scripts/page-template.html      the offline comparison page
  scripts/tapetube/               sigproc, osd, vhs (tape chain), crt (tube), presets, media, ffbin, pipeline, preview,
                                  page, rewind, selftest
tests/                            pytest suite
tools/fidelity_check.py           compares the tape chain with the reference looktest.py (needs that project and SciPy)
tools/package_skill.py            builds dist/vhs-crt-look-skill.zip
install.py                        installs from a checkout into ~/.claude/skills (or a project), then runs setup
docs/                             README images
AGENTS.md, CLAUDE.md, DESIGN.md   agent instructions and the comparison page's design notes
```

## Develop and test

```bash
uv sync                                              # or: python -m venv .venv && pip install -r vhs-crt-look/requirements.txt pytest ruff
.venv/bin/python -m pytest -q
.venv/bin/python vhs-crt-look/scripts/vhslook.py selftest --quick
.venv/bin/ruff check . && .venv/bin/ruff format --check . && pyright
```

`VHSLOOK_SLOW=1 pytest` also runs the quick self-test from pytest. CI runs doctor, the unit tests, a user-style install into a fresh home folder and the full self-test on Linux (Python 3.9 and 3.13).

## Release

The README's download link points at `releases/latest/download/vhs-crt-look-skill.zip`, so every release needs that asset:

```bash
python tools/package_skill.py                        # dist/vhs-crt-look-skill.zip
gh release create v1.1.0 dist/vhs-crt-look-skill.zip --title "v1.1.0" --notes "..."
```

## Fidelity

`tools/fidelity_check.py <reference project>` feeds identical frames to this tape chain and to the reference `looktest.py`. With seed 0 the final tape signal matches to within 6e-6 of full scale on all seven tape presets V1 to V7 (an 8-bit step is 3.9e-3). The tube is a numpy port of the reference three.js face shader with the same parameters.

## Agent files

`AGENTS.md` holds the instructions for coding agents; `CLAUDE.md` imports it for Claude Code.
