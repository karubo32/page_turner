#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$DIR/gui/page_turner_gui.py" &
disown %1
exit 0
