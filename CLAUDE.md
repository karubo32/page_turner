# CLAUDE.md — Claude Code 用プロジェクト指示書

## このプロジェクトについて

本めくり装置の制御システムです。以下の2つのコンポーネントで構成されます。

- **`gui/page_turner_gui.py`** — Python/tkinter GUIアプリ。pyserialでArduinoとシリアル通信
- **`firmware/bookv9/`** — Arduino Nanoファームウェア（4ファイル構成）

---

## ファームウェア構成 (firmware/bookv9/)

| ファイル | 内容 |
|---------|------|
| `bookv9.ino` | グローバル変数・可変設定・EEPROM・setup・loop |
| `motion.ino` | moveSmooth / tapMotion / yMotion / goHome |
| `calib.ino` | 補間・キャリブEEPROM・printOffsetTable |
| `commands.ino` | readSerialLine・checkSerialInput（全コマンド） |

---

## コードを編集する際の注意事項

### GUI (page_turner_gui.py)

- **シリアル通信は115200bps固定**（変更しない）
- `_parse_table_line()` はArduinoの `table` コマンド応答をパースする。  
  Arduino側の出力フォーマット `[<slot>] page <n>~: Z=<val>` と必ず対応させること
- `total_pages` / `CALIB_INTERVAL` はGUIとArduino側で値を合わせること（両方 **50** 固定）
- tkinterはスレッドセーフでないため、シリアル受信は別スレッド→`log_queue`→メインスレッドで処理する構造を維持すること
- `FlatButton` は `tk.Label` ベースのカスタムボタン。`tk.Button` に変更しないこと（スタイルが崩れる）
- 接続時に `_fetch_all()` が `pages` → `table` → `set` を順に送って自動取得する
- `_update_total_pages()` は総ページ数が変わった時だけテーブルを再構築する。  
  無条件に再構築すると取得済みのZ値が消えるため、このガードを外さないこと

### ファームウェア (bookv9/)

- **Z軸の角度は絶対角度で管理**（v9以降。オフセット方式ではない）
- `zOffsets[]` は各区間のZ絶対角度を格納する配列（名前がoffsetでも実態は絶対値）
- `getZHold()` はページ数に応じて130〜145°を返す関数。定数に戻さないこと
- EEPROMレイアウト:
  - addr 0: マジックバイト (0xAB)
  - addr 1〜11: zOffsets[0〜10]（CALIB_SECTIONS_MAX=11分）
  - addr 12〜14: 未使用（旧 testrun 保存領域）
  - addr 15〜17: totalPages保存 (magic + 2byte)
  - addr 18〜20: globalSpeed保存 (magic + value×100 の2byte)
  - addr 21〜29: 可変設定保存 (magic + 8値)。**項目数を変えたらマジックも変えること**
- `CALIB_SECTIONS_MAX = 11` を超える区間数には対応していない
- `moveSmooth()` のspeedScaleは呼び出しごとに調整済み。むやみに変更しないこと
- ページは**2ページ単位**で進む（currentPage += 2）
- 1ページの動作順は `tapMotion()` → `yMotion()` → `pressMotion()`。  
  `yMotion()` の末尾が `moveSmoothDual()` でY・Zを同時にホームへ戻す

### 可変設定（ホーム位置・サーボリミット）

`bookv9.ino` で **変数** として定義され、`set` コマンド／GUIの「詳細設定」から変更でき、
EEPROMに保存される。定数に戻さないこと。

```cpp
int Y_HOME = 90;       // Y軸待機位置
int Z_HOME = 90;       // Z軸待機位置
int Y_MIN  = 45;       // Y軸リミット
int Y_MAX  = 210;
int Z_MIN  = 1;        // Z軸リミット
int Z_MAX  = 180;
int PRESS_START = 168; // ページ押さえ角度（先頭ページ）
int PRESS_END   = 174; // ページ押さえ角度（最終ページ）
```

- `set` は `[SET] <name>=<value>` 形式で出力する。GUIの `_parse_table_line()` がこれをパースするので**書式を変えないこと**
- 設定名は `sscanf` の `%7s` で受けるため **7文字以内**にすること（`pstart` / `pend` はこの制約による短縮名）
- `MIN >= MAX` になる変更は拒否される
- 押さえ角度は `Z_MAX` を超えると `moveSmooth()` でクランプされる。既定の `Z_MAX = 180` はこれを見込んだ値
- `moveSmooth()` はサーボアドレスで軸を識別し、自動でリミットを適用する
- `writeY()` / `writeZ()` は constrain 付きの直接書き込みヘルパー

---

## よくある作業パターン

### キャリブ関連の修正
`firmware/bookv9/calib.ino` の `printOffsetTable()` と `gui/page_turner_gui.py` の `_parse_table_line()` / `_send_oz()` はセットで修正する。

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
