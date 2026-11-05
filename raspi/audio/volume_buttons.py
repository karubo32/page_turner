#!/usr/bin/env python3
"""Pirate Audio buttons change the speaker volume.

X (GPIO16) = volume up, Y (GPIO24) = volume down; hold to keep changing.
A and B are used by the page turner GUI (start/stop, back to page 1).
The volume is the ALSA softvol control "Master" from ~/.config/alsa/asoundrc and is
saved to ~/.config/pirate_volume so it survives reboots.
"""
import logging
import math
import struct
import subprocess
import wave
from pathlib import Path
from signal import pause

from gpiozero import Button

CARD = "sndrpihifiberry"
CONTROL = "Master"
STEP = 5          # percent per press / repeat
DEFAULT = 80
STATE_FILE = Path.home() / ".config" / "pirate_volume"
BEEP = Path.home() / ".cache" / "pirate_beep.wav"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


def load_volume() -> int:
    try:
        return max(0, min(100, int(STATE_FILE.read_text().strip())))
    except (OSError, ValueError):
        return DEFAULT


def set_volume(percent: int) -> None:
    subprocess.run(["amixer", "-q", "-c", CARD, "sset", CONTROL, f"{percent}%"], check=False)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(f"{percent}\n")
    logging.info("volume %d%%", percent)


def ensure_control() -> None:
    # softvol creates "Master" only after the device is opened once.
    probe = subprocess.run(["amixer", "-c", CARD, "sget", CONTROL], capture_output=True)
    if probe.returncode != 0:
        subprocess.run(["aplay", "-q", "-d", "1", "/dev/zero", "-f", "S16_LE", "-r", "48000"],
                       stderr=subprocess.DEVNULL, check=False)


def make_beep() -> None:
    # 80 ms 880 Hz tone with a short fade so it doesn't click.
    rate, n = 48000, 3840
    frames = bytearray()
    for i in range(n):
        env = min(1.0, i / 240, (n - i) / 240)
        frames += struct.pack("<h", int(12000 * env * math.sin(2 * math.pi * 880 * i / rate)))
    BEEP.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(BEEP), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


def beep() -> None:
    # Short confirmation sound at the new level; don't wait for it to finish.
    subprocess.Popen(["aplay", "-q", str(BEEP)], stderr=subprocess.DEVNULL)


volume = load_volume()


def change(delta: int) -> None:
    global volume
    new = max(0, min(100, volume + delta))
    if new != volume:
        volume = new
        set_volume(volume)
    beep()


make_beep()
ensure_control()
set_volume(volume)

up = Button(16, pull_up=True, bounce_time=0.05, hold_time=0.4, hold_repeat=True)
down = Button(24, pull_up=True, bounce_time=0.05, hold_time=0.4, hold_repeat=True)
up.when_pressed = up.when_held = lambda: change(+STEP)
down.when_pressed = down.when_held = lambda: change(-STEP)

logging.info("ready: X=up Y=down")
pause()
