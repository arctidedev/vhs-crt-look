# vhs-crt-look

The 1987 camcorder, VHS tape and CRT TV look from the short film **My Own Funeral**, as a free skill for Claude (and a plain command-line tool) that anyone can run on their own images and videos.

It is a signal model, not a filter: the picture goes through a consumer camcorder, an SP recording, a playback deck, optionally a dub, and then a CRT built per pixel (beam lines, phosphor mask, glow, glass) and the camera that filmed it. Every stage can be switched off or turned up or down, and every choice is previewed on your own media before the final render.

## What you need

- Python 3.9 or newer
- `numpy` and `opencv-python-headless` (`python -m pip install -r requirements.txt`)
- `ffmpeg` (with `ffprobe`) for video: macOS `brew install ffmpeg`, Windows `winget install Gyan.FFmpeg`, Debian/Ubuntu `sudo apt install ffmpeg`, conda `conda install -c conda-forge ffmpeg`. Stills work without it.

No GPU, browser or internet connection is needed. Works on macOS, Windows and Linux.

## Install as a Claude skill

**Claude Code:** copy this folder (`vhs-crt-look`, the one holding `SKILL.md`) into your skills folder:

- all projects: `~/.claude/skills/vhs-crt-look` (Windows: `%USERPROFILE%\.claude\skills\vhs-crt-look`)
- one project: `<project>/.claude/skills/vhs-crt-look`

or run `python install.py` from the repository root. Then ask Claude something like "make this clip look like a 1987 camcorder tape filmed off a TV" and point it at your file. Claude checks the setup, renders a contact sheet of every look on your footage plus a before/after page, asks what you want, iterates on previews and only then renders.

**Other Claude apps that accept custom skills:** upload a zip of this folder (`python tools/package_skill.py` in the repository builds `dist/vhs-crt-look-skill.zip`). Video needs an environment where ffmpeg is available.

## Use it without Claude

```
python scripts/vhslook.py doctor                          # check the setup
python scripts/vhslook.py preview clip.mp4 --open         # sheet + compare + ladder + clip + page
python scripts/vhslook.py render clip.mp4 out.mp4 --look church-dub -s noise=0.6 --date "JUL 4 1989"
python scripts/vhslook.py render photo.jpg out.png --look curved-80s-set
python scripts/vhslook.py rewind clip.mp4 rewind.mp4 --from 6 --to 2 --duration 2
python scripts/vhslook.py looks                           # every look, preset, strength and stage
python scripts/vhslook.py selftest --quick                # synthetic media through everything
```

`SKILL.md` has the complete option reference.

## What is modelled

**Tape:** lens and pickup softness, tungsten white balance, highlight bloom, CCD smear or tube lag, the camera's knee, AGC gain noise, the burned-in date in the camcorder's own 5x7 lettering, a 480-line interlaced raster, FM luma and colour-under chroma bandwidth in TV lines, the 1H chroma comb, tape luma and chroma noise, dropouts, chroma delay, time-base error (line jitter, tape-stretch wobble, top flagging, head-switching skew), edge-enhancement halos, head-switching noise, a tracking band, lifted VHS black, and second or third generations.

**Tube:** overscan, residual pincushion, rounded raster corners, 480 Gaussian beam lines whose width grows with beam current, beam defocus toward the corners, misconvergence, a slot, aperture-grille (with damper wires) or dot-triad mask as a band-limited Fourier series convolved with the filming camera's PSF (so it resolves only when the screen is large in frame and never aliases), white smear, faceplate bloom and halation, milky lift, tube black, the room's reflection and a lamp specular on the glass, the picture's light on the bezel, one recorded 240-line field, the refresh roll of an unsynced shutter, lens bloom, glare and camera grain.

**Rewind:** a VCR in visible search: noise bars rolling down, sideways sawtooth skew, head-switch bend, the deck accelerating and slowing.

## Credits and licence

Look and models by Raul Brito for **My Own Funeral** (GenHQ Weekly Challenge: Give Your Character a Voice, 2026). Released under the MIT licence (see `LICENSE`): use it, change it, ship it.
