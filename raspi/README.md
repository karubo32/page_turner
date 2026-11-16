# Raspberry Pi 側のファイル

本めくり装置のラズパイ（Raspberry Pi 5、ホスト名 `pi1`、ユーザー `jimaydev`）で動かしているものです。
Arduino のファームウェアは [`firmware/bookv9/`](../firmware/bookv9/) にあります。

| フォルダ | 中身 |
|---|---|
| [`gui/`](gui/) | ラズパイ用 GUI（800x480 の画面向け） |
| [`audio/`](audio/) | Pirate Audio の音と X / Y 音量ボタン（[説明](audio/README.md)） |
| [`lcd/`](lcd/) | Pirate Audio の液晶（240x240）に状態・ページ・認識結果を表示 |
| [`dev/`](dev/) | 開発中の確認用カメラ配信（ふだんは使わない） |

## gui/ — ラズパイ用 GUI

PC 用の [`gui/page_turner_gui.py`](../gui/page_turner_gui.py) をもとに、ラズパイの小さい画面と Pirate Audio のボタン向けに変えたものです。

- 起動したら Arduino に自動で接続（抜き差しすると自動でつなぎ直す）
- Settings 欄（待機・開始位置、めくり方、押さえ、待ち、動ける範囲）と Rewind 欄（1ページ目に戻る動き）
- Pirate Audio の A = 再生 / 停止、B = 1ページ目に戻る
- チェックボックス「UNMET と連動する」「最後まで行ったら最初から」
- 状態を `/run/user/1000/page_turner_status.json` に1秒ごとに書く（液晶表示が読む）

置き方:

```bash
mkdir -p ~/page_turner
cp gui/page_turner_gui.py ~/page_turner/
cp gui/page-turner.desktop ~/Desktop/
mkdir -p ~/.config/autostart && cp gui/page-turner.desktop ~/.config/autostart/   # 電源オンで自動起動
```

`page-turner.desktop` はユーザー名 `jimaydev` のパスを書いているので、ほかのユーザーで使うときは書き換えてください。

## lcd/ — 液晶表示

`pirate_display.py` が GUI の状態ファイルと、認識ソフト（UNMET）が書く結果ファイル `/run/user/1000/unmet_results.json` を読んで、0.5 秒ごとに表示します。認識ソフト本体はこのリポジトリには入っていません。

```bash
./lcd/setup_lcd.sh        # SPI を有効にして日本語フォントを入れる（再起動する）
./lcd/fix_lcd_spi.sh      # 液晶の DC ピン（GPIO9）を SPI から外す（再起動する）
cp lcd/pirate_display.py ~/
cp lcd/pirate-display.service ~/.config/systemd/user/
systemctl --user enable --now pirate-display
```

`st7789` ライブラリが入った Python で動かします（今は UNMET の venv を使っています）。

## dev/ — カメラ配信（開発用）

`http://pi1:8000/` でカメラのライブ映像、`/snap.jpg` で静止画が取れます。カメラを UNMET と取り合うので、使うときは UNMET を止めてください。今は無効にしてあります。
