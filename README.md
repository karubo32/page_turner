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
│       ├── bookv9.ino       # 設定・グローバル変数・EEPROM・setup・loop
│       ├── motion.ino       # サーボ動作関数
│       ├── calib.ino        # キャリブテーブル・補間・EEPROM
│       └── commands.ino     # シリアルコマンドパーサー
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
| `calib_reset` | キャリブデータ消去 |
| `t` / `tap` | タップ動作を1回 |
| `test <page>` | 指定ページのZ値で1ページ分動作 |
| `set` | 詳細設定の一覧表示 |
| `set <name> <val>` | 詳細設定の変更 |
| `pages <num>` | 総ページ数変更 |
| `help` | コマンド一覧 |

詳細は `docs/spec_v3.docx` を参照してください。

---

## 1ページめくりの動作

| 順 | 動作 | 内容 |
|----|------|------|
| 1 | `tapMotion()` | Z軸でページに触れて持ち上げる |
| 2 | `yMotion()` | Y軸でページを剥がしてめくる（末尾でY・Zを同時にホームへ） |
| 3 | `pressMotion()` | めくったページが浮くのでZ軸で押さえる |

---

## キャリブレーション概要

- **50ページごと**に区間を分けてZ軸の押し付け角度を管理（最大11区間）
- 区間間は線形補間で自動接続
- 設定値はEEPROMに保存（電源OFFでも保持）
- GUIのキャリブテーブルから各区間の角度を直接編集・送信
- 接続時にテーブルの値と総ページ数を**自動取得**

---

## 詳細設定（ホーム位置・サーボリミット）

GUI 左サイドバーの「⚙ 詳細設定」から変更できます。  
変更内容は Arduino の EEPROM に保存され、電源を切っても保持されます。

| 項目 | 説明 | 初期値 |
|------|------|--------|
| `yhome` | Y軸の待機角度 | 90 |
| `zhome` | Z軸の待機角度 | 90 |
| `ymin` / `ymax` | Y軸の可動範囲 | 45 / 210 |
| `zmin` / `zmax` | Z軸の可動範囲 | 1 / 180 |
| `pstart` / `pend` | ページ押さえ角度（先頭 / 最終ページ） | 168 / 174 |

リミットは自動動作・手動操作の**すべてに適用**され、サーボの破損を防ぎます。  
`MIN >= MAX` になる変更は拒否されます。

シリアルから直接変更する場合:

```
set              # 一覧表示
set yhome 95     # 変更
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
