# vhs-crt-look

A 1987 camcorder, VHS tape and CRT TV look as a free skill for Claude (and a plain command-line tool) that anyone can run on their own images and videos.

It is a signal model, not a filter: the picture goes through a consumer camcorder, an SP recording, a playback deck, optionally a dub, and then a CRT built per pixel (beam lines, phosphor mask, glow, glass) and the camera that filmed it. Every stage can be switched off or turned up or down, and every choice is previewed on your own media before the final render.

## Install (about two minutes)

1. Unzip `vhs-crt-look-skill.zip`.
2. Double-click the installer in the unzipped folder:
   - **Mac:** `INSTALL-mac.command`. The first time, macOS may block a downloaded file: right-click it, choose **Open**, then **Open** again.
   - **Windows:** `INSTALL-windows.bat`. If Windows shows "Windows protected your PC", click **More info**, then **Run anyway**.
   - **Linux:** open a terminal in the folder and run `bash install.sh`.
3. When it says **All set**, restart Claude Code and ask, for example: *"Make ~/Movies/birthday.mp4 look like an old VHS home video."*

The installer copies the skill into Claude Code (`~/.claude/skills/vhs-crt-look`), gives it its own Python packages (numpy and OpenCV, about 60 MB, nothing installed system-wide), and checks for ffmpeg, which video needs. If ffmpeg is missing it shows the one command that installs it and asks before running it. If Python is missing it says how to get it (on Windows it offers to install it).

**Even simpler:** in Claude Code, say *"Install the skill in ~/Downloads/vhs-crt-look-skill.zip"* and let Claude do the steps above.

Claude then does the rest each time: it renders every look on your own photo or clip, shows you a contact sheet and a before/after page, asks which look and how strong, refines the previews with you, and only then renders the final file.

**Requirements, for reference:** Python 3.9 or newer, numpy, opencv-python-headless, and ffmpeg (with ffprobe) for video. No GPU, browser or internet connection is needed after setup. macOS, Windows and Linux.

**Other Claude apps that accept custom skills:** upload the zip. Video there needs an environment with ffmpeg.

## Use it without Claude

```
python scripts/vhslook.py setup                           # one time: own environment, numpy, OpenCV, ffmpeg
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

By Raul Brito. Released under the MIT licence (see `LICENSE`): use it, change it, ship it.
