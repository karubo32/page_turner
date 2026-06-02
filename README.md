# 本めくり装置 — Page Turner Controller

自動ページめくり装置の制御システムです。  
Arduino Nano (ATmega328P) + サーボ2軸 + Python GUI で構成されます。

---

## プロジェクト構成

```
page_turner/
├── README.md
├── CLAUDE.md
├── launch_windows.vbs       # Windows 用起動ランチャー
├── launch_mac.command       # macOS 用起動ランチャー
├── gui/
│   └── page_turner_gui.py   # Python GUIアプリ (tkinter + pyserial)
├── firmware/
│   └── bookv9/              # Arduino スケッチフォルダ
│       ├── bookv9.ino       # 定数・グローバル変数・setup・loop
│       ├── motion.ino       # サーボ動作関数
│       ├── calib.ino        # キャリブレーション・EEPROM
│       ├── commands.ino     # シリアルコマンドパーサー
│       └── testrun.ino      # 全ページ通しテスト
└── docs/
    └── spec_v2.docx         # 機能仕様書
```

---

## クイックスタート

### 1. ドライバインストール (CH340)
https://sparks.gogo.co.nz/ch340.html

### 2. Arduinoへの書き込み
- ボード: `Arduino Nano`
- プロセッサ: `ATmega328P (Old Bootloader)`
- スケッチ: `firmware/bookv9/bookv9.ino`
- 通信速度: `115200 bps`

### 3. GUIの起動

**ターミナルなしで起動（推奨）**

| OS | 方法 |
|----|------|
| Windows | `launch_windows.vbs` をダブルクリック |
| macOS | `launch_mac.command` をダブルクリック（初回のみ `chmod +x launch_mac.command` が必要） |

**ターミナルから起動（開発用）**
```bash
pip install pyserial
python gui/page_turner_gui.py
```

---

## ハードウェア

| 項目 | 内容 |
|------|------|
| マイコン | Arduino Nano (ATmega328P Old Bootloader) |
| Y軸サーボ | D9ピン（剥がし軸） |
| Z軸サーボ | D10ピン（タップ軸） |
| 通信 | USB-Serial (CH340) / 115200 bps |

---

## 主要コマンド (シリアル / GUI)

| コマンド | 説明 |
|---------|------|
| `start` | 動作開始 |
| `stop` | 一時停止 |
| `home` | ホームポジションへ復帰 |
| `step` | ステップモード ON/OFF |
| `n` | 1ページ進む（stepモード時） |
| `speed <val>` | 速度変更 (0.1〜5.0) |
| `oz <slot> <angle>` | キャリブ角度を直接指定 |
| `table` | キャリブテーブル表示 |
| `calib` | インタラクティブキャリブレーション |
| `testrun` | 全ページ通しテスト |
| `pages <num>` | 総ページ数変更 |
| `help` | コマンド一覧 |

詳細は `docs/spec_v2.docx` を参照してください。

---

## キャリブレーション概要

- **50ページごと**に区間を分けてZ軸の押し付け角度を管理（最大11区間）
- 区間間は線形補間で自動接続
- 設定値はEEPROMに保存（電源OFFでも保持）
- GUIのキャリブテーブルから各区間の角度を直接編集・送信可能

---

## サーボ角度リミット

全動作（自動・手動）に共通のリミットが適用されます。  
変更は `firmware/bookv9/bookv9.ino` の定数のみ。

```cpp
const int Y_HOME = 90;   // Y軸待機位置
const int Z_HOME = 90;   // Z軸待機位置

const int Y_MIN = 45;    // Y軸リミット
const int Y_MAX = 135;
const int Z_MIN = 20;    // Z軸リミット
const int Z_MAX = 110;
```

---

## Z軸ホールド角度

ページ数に応じて自動で増加します。

```
先頭ページ: 130°
最終ページ: 145°
```

---

## 動作環境

- Python 3.x（tkinter標準付属）
- `pip install pyserial`
- Windows / macOS 対応
