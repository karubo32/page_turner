#!/usr/bin/env bash
# Enable SPI for the Pirate Audio LCD, install a Japanese+Latin font, then reboot.
set -euo pipefail
CONFIG=/boot/firmware/config.txt
sudo apt install -y fonts-noto-cjk
if ! grep -q '^dtparam=spi=on' "$CONFIG"; then
  sudo cp "$CONFIG" "$CONFIG.bak-$(date +%Y%m%d%H%M%S)"
  sudo sed -i 's/^#dtparam=spi=on/dtparam=spi=on/' "$CONFIG"
  grep -q '^dtparam=spi=on' "$CONFIG" || echo 'dtparam=spi=on' | sudo tee -a "$CONFIG" >/dev/null
fi
grep -n '^dtparam=spi' "$CONFIG"
echo "Rebooting in 3 seconds..."
sleep 3
sudo reboot
