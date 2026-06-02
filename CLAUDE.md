# CLAUDE.md — Claude Code 用プロジェクト指示書

## このプロジェクトについて

本めくり装置の制御システムです。以下の2つのコンポーネントで構成されます。

- **`gui/page_turner_gui.py`** — Python/tkinter GUIアプリ。pyserialでArduinoとシリアル通信
- **`firmware/bookv9/`** — Arduino Nanoファームウェア（5ファイル構成）

---

## ファームウェア構成 (firmware/bookv9/)

| ファイル | 内容 |
|---------|------|
| `bookv9.ino` | グローバル変数・定数・setup・loop |
| `motion.ino` | moveSmooth / tapMotion / yMotion / goHome / wiperMotion |
| `calib.ino` | EEPROM・補間・printOffsetTable・runCalibration |
| `commands.ino` | readSerialLine・checkSerialInput（全コマンド） |
| `testrun.ino` | saveTestrunState・clearTestrunState・runTestrun |

---

## コードを編集する際の注意事項

### GUI (page_turner_gui.py)

- **シリアル通信は115200bps固定**（変更しない）
- `_parse_table_line()` はArduinoの `table` コマンド応答をパースする。  
  Arduino側の出力フォーマット `[<slot>] page <n>~: Z=<val>` と必ず対応させること
- `total_pages` / `CALIB_INTERVAL` はGUIとArduino側で値を合わせること（両方 **50** 固定）
- tkinterはスレッドセーフでないため、シリアル受信は別スレッド→`log_queue`→メインスレッドで処理する構造を維持すること
- `FlatButton` は `tk.Label` ベースのカスタムボタン。`tk.Button` に変更しないこと（スタイルが崩れる）

### ファームウェア (bookv9/)

- **Z軸の角度は絶対角度で管理**（v9以降。オフセット方式ではない）
- `zOffsets[]` は各区間のZ絶対角度を格納する配列（名前がoffsetでも実態は絶対値）
- `getZHold()` はページ数に応じて130〜145°を返す関数。定数に戻さないこと
- EEPROMレイアウト:
  - addr 0: マジックバイト (0xAB)
  - addr 1〜11: zOffsets[0〜10]（CALIB_SECTIONS_MAX=11分）
  - addr 12〜14: testrunモード保存
  - addr 15〜17: totalPages保存 (magic + 2byte)
  - addr 18〜20: globalSpeed保存 (magic + value×100 の2byte)
- `CALIB_SECTIONS_MAX = 11` を超える区間数には対応していない
- `moveSmooth()` のspeedScaleは呼び出しごとに調整済み。むやみに変更しないこと
- ページは**2ページ単位**で進む（currentPage += direction * 2）
- testrunも**2ページ単位**（testrunPage += 2）

### サーボ角度リミット

全動作（自動・手動）に共通のリミットが `bookv9.ino` に定義されている。  
変更は以下の4定数のみ。**Y_MIN ≤ Y_HOME ≤ Y_MAX**、**Z_MIN ≤ Z_HOME ≤ Z_MAX** を守ること。

```cpp
const int Y_HOME = 90;   // Y軸待機位置
const int Z_HOME = 90;   // Z軸待機位置

const int Y_MIN = 45;    // Y軸リミット（物理角度）
const int Y_MAX = 210;
const int Z_MIN = 20;    // Z軸リミット（物理角度）
const int Z_MAX = 160;
```

- `moveSmooth()` はサーボアドレスで軸を識別し、自動でリミットを適用する
- `writeY(logicalAngle)` / `writeZ(logicalAngle)` は applyDirection + constrain をまとめたヘルパー。直接書き込みにはこちらを使う

---

## よくある作業パターン

### キャリブ関連の修正
`firmware/bookv9/calib.ino` の `runCalibration()` と `gui/page_turner_gui.py` の `_parse_table_line()` / `_send_oz()` はセットで修正する。

### コマンド追加
1. `firmware/bookv9/commands.ino` の `checkSerialInput()` にコマンド処理を追加
2. 同ファイルの `help` 出力にも追加
3. 必要に応じてGUI側にボタン/ハンドラを追加

### GUI レイアウト変更
- 左サイドバー: `_build_sidebar()` 内のカードを追加・削除
- 右パネル: `_build_main()` → キャリブテーブルは `_build_calib_table()` / ログは `_build_log()`
- カラーテーマ: ファイル冒頭のトークン定数（`BG`, `SURFACE`, `BLUE` など）を変更

---

## 起動方法

```bash
# GUI（ターミナルあり・開発用）
python gui/page_turner_gui.py

# GUI（ターミナルなし・Windows）
launch_windows.vbs をダブルクリック

# GUI（ターミナルなし・macOS）
# 初回のみ: chmod +x launch_mac.command
launch_mac.command をダブルクリック

# Arduinoへ書き込み
# ボード: Arduino Nano / ATmega328P (Old Bootloader) / 115200bps
# スケッチ: firmware/bookv9/bookv9.ino
```

---

## 依存関係

```
Python:  pyserial
Arduino: Servo.h, EEPROM.h（標準ライブラリ）
```
