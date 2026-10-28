# DESIGN.md

The only UI in this project is the offline comparison page the CLI writes (`vhs-crt-look/scripts/tapetube/page.py`): one self-contained HTML file per preview, opened from disk, no network.

## Intent

A place to judge a look on your own frame. The image is the hero; the chrome stays quiet and out of the way. Identity comes from the film itself, not from decoration.

## Tokens (CSS custom properties in page.py)

- Surround: `--bg #0d0d0c`, surfaces `--surface #151514`, `--surface-2 #1c1c1a`, hairlines `--line #2a2a27`. Neutral dark on purpose: images are judged against a neutral surround, as in a grading suite. Dark only.
- Text: `--ink #eeede8` (the OSD ink, 0.97 0.97 0.95), `--ink-dim #a3a29b`, `--ink-faint #6f6e68`.
- One accent: `--rec #e23b2e`, the camcorder's REC tally. Used only to mark the selected look or stage.
- Spacing: 4 / 8 / 12 / 16 / 24 / 32 / 48 px. Radius: 4 px controls, 6 px tiles and viewer.
- Type: system sans stack for UI text (14 px body, 12.5 px small), system monospace for commands. Display lettering is the camcorder OSD font (5x7 squared glyphs, the same table as the date stamp) drawn as inline SVG: page wordmark, the selected look's name, section heads, image corner labels.

## Layout

Single column, max 1400 px: viewer, look details with the exact render command, looks grid, stage ladder (tape S0 to S5, tube L0 to L6 and a phosphor macro), optional preview clip, footer. Tiles exist only where the tile is the item (a look, a stage).

## Interaction

- Before/after: drag on the image or use the range input under it; arrow keys step it; holding Space shows the original; keys 1 to 9 pick a look.
- Fit or 100 % pixels. Before = Original or Previous stage (when a stage is selected, so each stage's contribution can be seen alone).
- Every interactive element has a `data-testid`.

## Do not

Gradients, glows, glass panels, purple-blue accents, viewport-scaled type, negative letter spacing, decorative motion, network fonts or scripts.
