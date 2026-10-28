#!/bin/bash
# Double-click to install the vhs-crt-look skill for Claude Code.
# The first time, macOS may refuse to open a downloaded file: right-click this file, choose Open, then Open again.
cd "$(dirname "$0")" || exit 1
bash ./install.sh
echo
read -n 1 -s -r -p "Press any key to close this window."
echo
