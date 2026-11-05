# Pirate Audio（音とボタン）— Raspberry Pi 用

本めくり装置のラズパイ（Raspberry Pi 5 + Pimoroni Pirate Audio）で、スピーカーから音を出し、
X / Y ボタンで音量を変えるための設定です。

| ファイル | 置き場所 | 内容 |
|---|---|---|
| `config.txt.snippet` | `/boot/firmware/config.txt` に追記（sudo） | DAC（hifiberry-dac）とアンプの電源（GPIO25） |
| `asoundrc` | `~/.config/alsa/asoundrc` | 既定の出力を Pirate Audio へ。ソフト音量 `Master` と、複数のソフトの音を同時に出す dmix |
| `51-release-pirate-audio.conf` | `~/.config/wireplumber/wireplumber.conf.d/` | デスクトップの音声システムが Pirate Audio を占有しないようにする |
| `volume_buttons.py` | `~/volume_buttons.py` | X = 音量を上げる、Y = 下げる（押しっぱなしで連続、1回 5%）。ピッと鳴って確認でき、値は `~/.config/pirate_volume` に保存 |
| `volume-buttons.service` | `~/.config/systemd/user/` | 電源を入れたら `volume_buttons.py` を自動で起動 |
| `install.sh` | — | config.txt 以外をまとめて置いて、自動起動を有効にする |

A / B ボタンは本めくり装置の GUI が使います（A = 再生 / 停止、B = 1ページ目に戻る）。

## 入れ方

```bash
sudo apt install python3-gpiozero alsa-utils
# /boot/firmware/config.txt に config.txt.snippet の2行を追記してから
sudo reboot
# 再起動後
./install.sh
speaker-test -c 2 -t sine -l 1     # 音が出れば OK
```

## メモ

- asoundrc を `~/.asoundrc` に置くと、デスクトップの音量メニューが消してしまうことがあるため `~/.config/alsa/` に置いています
- Pi 5 では dmix の `format` / `channels` / `period_size` / `buffer_size` を指定しないとエラー（524）になります
- 音量はコマンドでも変えられます: `amixer -c sndrpihifiberry sset Master 80%`
