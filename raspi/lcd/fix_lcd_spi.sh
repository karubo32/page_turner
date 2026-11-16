#!/usr/bin/env bash
# Pirate Audio LCD uses GPIO9 (SPI0 MISO) as its DC pin: free it from SPI, then reboot.
set -euo pipefail
CONFIG=/boot/firmware/config.txt
if ! grep -q '^dtoverlay=spi0-2cs,no_miso' "$CONFIG"; then
  sudo cp "$CONFIG" "$CONFIG.bak-$(date +%Y%m%d%H%M%S)"
  printf '\n# Pirate Audio LCD: GPIO9 is the display DC pin, so SPI0 must not claim MISO\n[all]\ndtoverlay=spi0-2cs,no_miso\n' | sudo tee -a "$CONFIG" >/dev/null
fi
grep -n 'spi' "$CONFIG"
echo "Rebooting in 3 seconds..."
sleep 3
sudo reboot
