"""One-time setup, standard library only (it runs before numpy or OpenCV exist).

  python vhslook.py setup            create the skill's own Python environment, install numpy and OpenCV into it,
                                     find ffmpeg (and offer to install it), then check everything
  python vhslook.py setup --yes      the same, and install ffmpeg without asking if it is missing
  python vhslook.py setup --no-ffmpeg   skip the ffmpeg step (stills only)
  python vhslook.py setup --force    rebuild the environment from scratch

The environment lives in the skill folder (.venv), so nothing is installed into the system Python and the
"externally managed environment" errors of Homebrew and recent Linux Pythons never come up. vhslook.py switches
to it by itself, whichever python starts it.
"""

from __future__ import annotations

import os
import subprocess
import sys
import venv

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
VENV = os.path.join(SKILL_DIR, ".venv")
VENV_PY = os.path.join(VENV, "Scripts", "python.exe") if os.name == "nt" else os.path.join(VENV, "bin", "python")
REQ = os.path.join(SKILL_DIR, "requirements.txt")
sys.path.insert(0, HERE)

from tapetube import ffbin  # noqa: E402  (standard library only)


def say(msg=""):
    print(msg, flush=True)


def step(n, total, msg):
    say(f"[{n}/{total}] {msg}")


def ask(question: str, default_yes: bool = True) -> bool:
    if not sys.stdin or not sys.stdin.isatty():
        return False
    try:
        a = input(f"{question} [{'Y/n' if default_yes else 'y/N'}] ").strip().lower()
    except EOFError:
        return False
    return default_yes if not a else a.startswith("y")


def env_works() -> bool:
    if not os.path.exists(VENV_PY):
        return False
    r = subprocess.run([VENV_PY, "-c", "import numpy, cv2"], capture_output=True)
    return r.returncode == 0


def make_env(force: bool) -> bool:
    if force or not os.path.exists(VENV_PY):
        try:
            venv.EnvBuilder(with_pip=True, clear=force).create(VENV)
        except Exception as e:  # noqa: BLE001  (Debian/Ubuntu ship venv without ensurepip)
            say(f"   Could not create a Python environment: {e}")
            if sys.platform.startswith("linux"):
                v = f"{sys.version_info[0]}.{sys.version_info[1]}"
                say(f"   Fix: sudo apt install python{v}-venv   (or python3-venv), then run setup again.")
            return False
    say("   Installing numpy and OpenCV (one time, about 60 MB)...")
    cmd = [VENV_PY, "-m", "pip", "install", "--disable-pip-version-check", "--quiet", "-r", REQ]
    r = subprocess.run(cmd)
    if r.returncode != 0:
        say("   The install failed. Check the internet connection and run setup again.")
        return False
    return env_works()


def ffmpeg_step(yes: bool, skip: bool) -> bool:
    ff, fp = ffbin.find("ffmpeg"), ffbin.find("ffprobe")
    if ff and fp:
        say(f"   Found ffmpeg: {ff}")
        return True
    if skip:
        say("   Skipped. Still images work; video needs ffmpeg.")
        return True
    cmd = ffbin.install_command()
    if not cmd:
        say("   ffmpeg is not installed, and no package manager was found to install it.")
        say("   " + ffbin.manual_hint())
        say("   Still images work without it; video needs it. Run setup again afterwards.")
        return False
    say("   ffmpeg is not installed. It is needed for video (still images work without it).")
    say("   This command installs it:  " + " ".join(cmd))
    if not (yes or ask("   Install ffmpeg now?")):
        say("   Not installed. Run that command yourself, or run setup again with --yes.")
        return False
    r = subprocess.run(cmd)
    if r.returncode != 0:
        say("   The ffmpeg install did not finish. " + ffbin.manual_hint())
        return False
    ff, fp = ffbin.find("ffmpeg"), ffbin.find("ffprobe")
    if ff and fp:
        say(f"   Installed: {ff}")
        return True
    say("   ffmpeg was installed but is not visible yet. Open a new terminal (or restart Claude) and run setup again.")
    return False


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    yes, force, skip = "--yes" in argv or "-y" in argv, "--force" in argv, "--no-ffmpeg" in argv
    say("Setting up vhs-crt-look")
    if sys.version_info < (3, 9):
        say(
            f"Python 3.9 or newer is needed; this is {sys.version.split()[0]}. Install it from https://www.python.org/downloads/"
        )
        return 1
    step(1, 3, "Python packages (numpy, OpenCV) in the skill's own environment")
    if env_works() and not force:
        say(f"   Already set up: {VENV}")
    elif not make_env(force):
        return 1
    else:
        say(f"   Ready: {VENV}")
    step(2, 3, "ffmpeg (for video)")
    ff_ok = ffmpeg_step(yes, skip)
    step(3, 3, "Final check")
    r = subprocess.run([VENV_PY, os.path.join(HERE, "vhslook.py"), "doctor"], env=dict(os.environ, VHSLOOK_IN_VENV="1"))
    say()
    if r.returncode == 0 and ff_ok:
        say("All set. Restart Claude Code (or start a new chat), then ask for example:")
        say('   "Make ~/Movies/birthday.mp4 look like an old VHS home video."')
        return 0
    if r.returncode == 0:
        say("Ready for still images. Install ffmpeg as shown above for video.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
