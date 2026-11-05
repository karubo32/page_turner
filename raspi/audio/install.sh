#!/bin/sh
# Pirate Audio sound + volume buttons for the page turner Raspberry Pi.
# Run as the desktop user (not root). /boot/firmware/config.txt is changed by hand: see config.txt.snippet.
set -e
cd "$(dirname "$0")"

install -m 755 volume_buttons.py "$HOME/volume_buttons.py"
install -D -m 644 asoundrc "$HOME/.config/alsa/asoundrc"
install -D -m 644 51-release-pirate-audio.conf \
    "$HOME/.config/wireplumber/wireplumber.conf.d/51-release-pirate-audio.conf"
install -D -m 644 volume-buttons.service "$HOME/.config/systemd/user/volume-buttons.service"

systemctl --user daemon-reload
systemctl --user restart wireplumber || true
systemctl --user enable --now volume-buttons.service
echo "Done. Test with: speaker-test -c 2 -t sine -l 1"
