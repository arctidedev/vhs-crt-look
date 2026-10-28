---
name: vhs-crt-look
description: Apply a physically modelled 1987 camcorder, VHS tape and CRT TV look to the user's own images and videos. Use whenever someone wants footage or stills to look like an old home video, a camcorder tape, a VHS copy or dub, a worn or EP tape, footage filmed off an old TV, scanlines or a phosphor mask, a camcorder date stamp, a VCR rewind, or a retro 80s or 90s video look. Runs locally on any OS with Python, numpy, OpenCV and ffmpeg. Always previews several looks on the user's own media and asks which one before the final render.
---

# VHS, camcorder and CRT look

A deterministic signal model, not a filter stack. The picture goes through what a real 1987 chain did to it:

- **Tape (S1 to S5):** a consumer camcorder (lens softness, tungsten white balance, highlight bloom, knee, AGC gain noise, the burned-in date), the 480-line interlaced raster, an SP recording (FM luma and colour-under chroma bandwidth in TV lines, tape noise, dropouts), the playback deck (time-base error, edge-enhancement halos, head-switching noise) and optionally a deck-to-deck dub.
- **Tube (L0 to L6):** a CRT built per pixel in linear light: 480 Gaussian beam lines whose width follows beam current, a slot, aperture-grille or dot-triad phosphor mask band-limited by the filming camera, faceplate bloom and halation, the front glass, the tube's light on its bezel, and the camera that filmed it (one recorded field, the refresh roll, lens bloom, grain).

Everything runs from `scripts/vhslook.py` in this skill's folder. Below, `VHSLOOK` means `python3 <this skill's folder>/scripts/vhslook.py` (on Windows `python` or `py -3`). It switches to the skill's own Python environment by itself. Quote paths with spaces.

## 1. First use: make sure it is set up

```
VHSLOOK doctor
```

- If it says the skill is not set up (numpy or OpenCV missing), run `VHSLOOK setup`. It creates the skill's own Python environment inside the skill folder and installs numpy and OpenCV there (about 60 MB, one time, nothing system-wide), then checks everything. Tell the user it is a one-time step.
- If ffmpeg is missing, setup prints the single command that installs it on this machine. Ask the user, and on a yes run `VHSLOOK setup --yes`. Stills work without ffmpeg; video needs it.
- If Python itself is missing or older than 3.9, point the user to the installer that came with the skill (`Install on Mac.command`, `Install on Windows.bat` or `install.sh`) or to python.org.
- The skill's own packages (numpy, OpenCV in its private folder) are part of setting it up. Never install system software (ffmpeg, Python, package managers) without asking.

## 2. The workflow (follow it every time)

1. **Get the media.** Ask for the file path(s) if not given. Run `VHSLOOK info <file>` and tell the user what it is in one line (size, length, frame rate, VFR, audio, alpha, portrait).
2. **Preview before anything else.** Run:
   ```
   VHSLOOK preview <file> --out <folder next to the file or in the working dir>
   ```
   (for a video add `--time <seconds>` at a representative moment). It writes, in one folder:
   - `sheet.jpg`: every look on the user's frame, labelled with its `--look` name
   - `compare/split.png`, `compare/side_by_side.png`, `compare/zoom.png`: before/after for the current look
   - `ladder/ladder_tape.png` and `ladder/ladder_tube.png`: the look built up one stage at a time
   - `clip_side_by_side.mp4` (video only): three seconds of original and look side by side
   - `page.html`: one offline page with all of it, a before/after slider, the stage ladder and the exact render command per look. No network needed; it can be emailed or opened anywhere.
3. **Show it.** Look at `sheet.jpg` yourself (read the image) so you can describe the differences. Give the user the absolute paths. If your client can display images or files, show the sheet and the split. Offer to open the page in their browser (`preview ... --open`, or open `page.html`).
4. **Ask, do not assume.** Ask which look they want, offering three or four that suit their footage plus "something else". Then ask only what matters for their case:
   - captured straight from the deck (`--capture direct`), the TV screen captured cleanly (`screen`), or filmed off a TV with a camera (`filmed`)
   - date stamp: keep, change the text (`--date "JUL 4 1989"`), move it (`--date-pos tl`) or remove it (`--no-date`)
   - strength of the damage (see the strengths table), tube mask type, curvature, how much bezel shows (`--fill`)
   - for portrait or non-4:3 media: keep the shape (`--frame native`, default), crop to 4:3 (`crop43`) or pad to 4:3 (`pad43`)
5. **Iterate on previews, never on the final.** For each change re-run the cheap previews with the same options: `VHSLOOK compare <file> <dir> [options]` (a still), `VHSLOOK ladder <file> <dir> [options]` (stages), `VHSLOOK clip <file> <out.mp4> --side-by-side [options]` (motion; 540 p, 3 s). Show each result and ask again until they are happy.
6. **Render.** Show the exact command, give a time estimate (the preview clip prints its frames per second; scale by the pixel count; `--quality high` is about 4 to 5 times slower on video), then run:
   ```
   VHSLOOK render <in> <out> [the agreed options]
   ```
   For long videos run it in the background and report progress. Output keeps the input's size and frame rate unless asked (`--height`, `--fps`).
7. **Verify and report.** Run `VHSLOOK info <out>` and check size, frame rate, duration against the source, and that audio is present when the source had it. Give the user the absolute output path and the command used so they can re-render later.

## 3. Options

### Named looks (`--look`)

| look | what it is |
|---|---|
| `vhs-on-tv` (default) | the full chain: second-generation SP dub on a slot-mask TV, filmed with a camera |
| `church-dub` | the same tape alone: second-generation SP dub, captured from the deck |
| `home-camcorder` | camcorder original on SP, captured from the deck |
| `clean-deck` | the cleanest picture that still reads as VHS |
| `ep-longplay` | six-hour EP copy: soft, noisy, dull colour |
| `worn-tape` | played hundreds of times: dropouts, tracking band, wobble, faded colour |
| `tube-camcorder` | pickup-tube camera under hot light: bloom and comet tails |
| `ccd-gain-up` | dim-room CCD camcorder: gain noise, vertical smear through lights |
| `consumer-tv` | camcorder tape on a slot-mask set, screen captured cleanly |
| `filmed-tv` | the same filmed with a camera, bezel in frame |
| `trinitron` | aperture-grille tube: stripes, damper wires |
| `sharp-scanlines` | well-focused tube, visible line gaps |
| `tired-tube` | old hot-driven tube: fat beam, heavy halation, misconvergence |
| `curved-80s-set` | curved dot-mask set of the era, bezel in frame, filmed |
| `washed-out-tv` | milky faceplate, lifted blacks, cool white, filmed |
| `hot-bloomy-tv` | brightness up, whites bloom and smear, filmed |

Build your own: `--tape V1..V7`, `--tube C1..C5` (or `none`), `--treatment T0..T6`, `--capture direct|screen|filmed`. `VHSLOOK looks` lists them all with descriptions.

### Strengths (`-s NAME=X`, repeatable; 1 = the preset, 0 = off, 2 = double)

| name | controls |
|---|---|
| `noise` | tape and camera noise |
| `dropouts` | dropouts per frame |
| `wobble` | time-base error: jitter, tape-stretch wobble, top flagging, head-switching skew, tracking band |
| `halos` | playback edge-enhancement halos |
| `softness` | bandwidth loss (TV lines divided by X; 0 = full sharpness) |
| `bleed` | colour bleed and chroma delay |
| `fade` | colour fade and lifted blacks |
| `warmth` | camcorder white balance away from neutral |
| `bloom` | camcorder highlight bloom |
| `scanlines` | beam-line visibility on the tube (0 = no line structure) |
| `mask` | phosphor mask contrast |
| `glow` | faceplate bloom and halation |
| `reflection` | the room and lamp reflected in the glass |
| `roll` | the filming camera's refresh roll bar |
| `lens` | the filming camera's lens bloom and glare |
| `grain` | the filming camera's grain |
| `lift` | milky faceplate scatter |

Example: `-s noise=0.5 -s dropouts=0 -s halos=1.5`.

### Other options

- `--off a,b`: switch stages off: `camcorder, date, record, playback, dub, beams, mask, glow, glass, light, camera`.
- `--gens N`: tape generations (1 original, 2 a dub, 3 a dub of a dub).
- `--mask slot|grille|dot|none`, `--curvature 0..1` (0 flat 2000s tube, 1 curved 1980s set), `--fill X` (1 = raster edge to edge, 0.85 shows the bezel, 1.3 zooms in).
- `--frame native|crop43|pad43`, `--width` / `--height` (aspect kept), `--quality standard|high` (high renders the tube at 2x and downsamples; default for stills, standard for video, nearly identical at normal viewing size).
- `--mix 0..1`: blend with the original. `--seed N`: different noise (0 = the reference noise); same seed, same output.
- `--reflection IMAGE`: an image the TV glass mirrors (the room behind the camera).
- `--set section.key=value`: any raw parameter, for example `--set vhs.luma_tvl=[200,180]` or `--set crt.overscan=1.0` (a TV crops about 7 % of the edges by default; this turns that off). `VHSLOOK params [options]` prints every resolved value.
- Video: `--start`, `--duration`, `--fps`, `--audio copy|aac|vhs|tv|none` (copy is the default and keeps the source audio untouched when the container allows; `vhs` gives it the camcorder's linear track, `tv` plays it out of a small TV speaker), `--codec h264|prores`, `--crf`, `--jobs`.
- `VHSLOOK rewind <in> <out> --from 6 --to 2 --duration 2 [options]`: a VCR rewind-search shot (noise bars, skew, the deck speeding up and slowing down) through the same look.

## 4. Media handling

- Any size and aspect, odd sizes included. Portrait stays portrait (480 lines over the picture height, the line length follows the width), unless `--frame crop43|pad43`. A 9:16 frame therefore carries about 400 samples across its width and looks softer than a 4:3 one, as a vertical crop of a real TV picture would; say so when previewing portrait media.
- Stills: PNG, JPEG (EXIF rotation honoured), TIFF, WebP, BMP, 16-bit PNG/TIFF (kept 16-bit), grayscale. Transparent images keep their alpha (the picture is composited over black before the tape, the alpha is carried through the tube's geometry).
- Video: anything ffmpeg reads. Rotation metadata and non-square pixels are applied. Variable frame rate becomes constant at the source's average rate (or `--fps`). Output dimensions are rounded to even numbers for H.264. Frames stream through ffmpeg pipes and worker processes, so length is limited by time, not memory. Audio is put back under the picture with the same trim.
- Output never overwrites the input; write next to it with a suffix unless the user names a path.

## 5. Speed

Measured on an Apple M5 Pro with the default 8 worker processes, at about 2 megapixels per frame (1664x1248): tape-only looks about 23 frames per second; tube looks about 5 at standard quality and about 1.2 at high. Other machines scale with core count and memory bandwidth. For long videos suggest a short `--start/--duration` test first, and `--height 720` when the full size is not needed.

## 6. Troubleshooting

- "not set up yet" or a missing `cv2` / `numpy`: run `VHSLOOK setup` (add `--force` to rebuild a broken environment).
- "ffmpeg is needed for video": run `VHSLOOK setup` (it offers to install ffmpeg), or set `VHSLOOK_FFMPEG` and `VHSLOOK_FFPROBE`. ffmpeg installed but not found: setup also looks in the usual Homebrew, winget, Chocolatey, Scoop and conda folders; otherwise restart the terminal or Claude.
- `libx264` missing: the skill falls back to another H.264 encoder or MPEG-4; doctor reports which.
- Slow: keep `--quality standard`, use `--height 720`, or raise `--jobs` toward the core count if memory allows.
- Verify an install end to end: `VHSLOOK selftest --quick` builds synthetic media and runs every look and output type.

## 7. Fidelity

The tape chain is a line-for-line port of the reference look-development code; on the same source frames it reproduces the reference tape signal to within 6e-6 of full scale with seed 0, on all seven tape presets. The tube is a numpy port of the reference three.js tube shader, with the same parameters.
