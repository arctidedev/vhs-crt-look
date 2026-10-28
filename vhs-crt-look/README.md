# VHS + CRT look for Claude

Make any photo or video look like a 1987 home video played on an old TV, just by asking Claude. Free, and it runs on your own computer.

## Install (a minute or two)

You need **Claude Code** (the **Code** tab in the Claude desktop app works too).

1. Double-click the installer in this folder:
   - **Install on Mac** on a Mac
   - **Install on Windows** on Windows (if you opened the zip without extracting it, right-click the zip, choose **Extract All**, and use the extracted folder)
   - On Linux, open a terminal in this folder and run `bash install.sh`
2. Wait until it says **All set**.
3. Start a new chat in Claude Code.

**Even easier:** open Claude Code and say *"Install the VHS skill from this folder: "* followed by where this folder is (for example `~/Downloads/vhs-crt-look`). Claude does the steps for you.

**If something gets in the way:**

- **Mac says it can't open "Install on Mac":** click **Done**, open **System Settings > Privacy & Security**, scroll down and click **Open Anyway**. On older macOS, right-click the file and choose **Open** instead.
- **Windows says "Windows protected your PC":** click **More info**, then **Run anyway**.
- **Python is missing:** on a Mac, if a window offers the *command line developer tools*, click **Install** and run the installer again when it's done. On Windows, the installer offers to install Python: say yes. Or get it from [python.org/downloads](https://www.python.org/downloads/).
- **ffmpeg is missing** (needed for video, not photos): the installer shows the command that installs it and asks first. Type **y** and press Enter.

The installer copies this folder to `~/.claude/skills/vhs-crt-look` (Windows: `%USERPROFILE%\.claude\skills\vhs-crt-look`) and gives it its own Python packages there (about 60 MB, nothing system-wide). Run it again any time to update.

## Use it

Start a new chat in Claude Code and ask, for example:

> Make ~/Movies/birthday.mp4 look like an old VHS home video.

> Make this photo look like it was filmed off an old TV: ~/Desktop/portrait.jpg

Claude shows you all 16 looks on your own photo or clip and a before/after page, asks which one and how strong, shows a preview, and then makes the final file next to your original. Your original is never changed.

## Uninstall

Delete the folder `~/.claude/skills/vhs-crt-look` (Windows: `%USERPROFILE%\.claude\skills\vhs-crt-look`).

## Without Claude

It's also a command-line tool. From this folder:

```
python3 scripts/vhslook.py setup                          # one time
python3 scripts/vhslook.py preview my-clip.mp4 --open     # every look on your clip, in a page
python3 scripts/vhslook.py render my-clip.mp4 my-clip-vhs.mp4 --look worn-tape
python3 scripts/vhslook.py looks                          # all looks and options
```

`SKILL.md` has every option.

## Note for Claude

If someone asks you to install this skill:

1. If you were given the zip, unzip it first (for example into the Downloads folder) and work in the unzipped `vhs-crt-look` folder, the one holding this file.
2. Run the installer from that folder:
   - macOS and Linux: `bash install.sh`
   - Windows: `cmd /c "Install on Windows.bat" --no-pause`
3. If it reports that ffmpeg is missing, it prints the command that installs it. Ask the user. On a yes, run the installer again with `--yes` (Windows: `cmd /c "Install on Windows.bat" --yes`).
4. When it prints **All set**, tell the user to start a new chat. The skill is then in `~/.claude/skills/vhs-crt-look`.

---

Made by Raul Brito. Free under the MIT licence (see `LICENSE`).
