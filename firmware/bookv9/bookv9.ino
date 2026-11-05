/*
本めくり装置 — Page Turner Controller
Arduino Nano (ATmega328P Old Bootloader) / 115200 bps
Y軸: D9（剥がし軸）/ Z軸: D10（タップ軸）
*/

#include <Servo.h>
#include <EEPROM.h>

Servo yaxis;
Servo zaxis;

// ===== 前方宣言 =====
// Arduino IDEの自動プロトタイプ生成は Servo& 参照とデフォルト引数を
// 正しく扱えないため、他タブの関数はここで明示的に宣言する
void  moveSmooth(Servo& servo, int startPos, int endPos, float speedScale = 1.0);
void  moveSmoothDual(int yStart, int yEnd, int zStart, int zEnd, float speedScale = 1.0);
void  goHome();
void  tapMotion();
void  yMotion();
void  pressMotion();

int   getSectionIndex(int page);
float getInterpolatedZ(int page);
int   getZTarget();
void  saveCalibToEEPROM();
bool  loadCalibFromEEPROM();
void  printOffsetTable();

int   readSerialLine(char* buf, int bufSize);
void  checkSerialInput();

void  loadRewindFromEEPROM();
bool  handleRewindCommand(const char* cmd);

// ===== 本情報 =====
int totalPages  = 180;    // pages コマンドで変更可能
int currentPage = 1;

// ===== 可変設定（set コマンド / GUIの詳細設定から変更・EEPROM保存）=====
int Y_HOME = 90;    // Y軸待機位置
int Z_HOME = 90;    // Z軸待機位置
int Y_MIN  = 45;    // Y軸リミット（下限）
int Y_MAX  = 210;   // Y軸リミット（上限）
int Z_MIN  = -14;   // Z軸リミット（下限・マイナス可。下の Z_PULSE_FLOOR が物理的な限界）
int Z_MAX  = 190;   // Z軸リミット（上限・180超も可。下の Z_PULSE_CEIL が物理的な限界）

// ===== Z軸のパルス幅制御 =====
// Servo.write() は 0〜180 にクランプされるため 0° 未満・180° 超へ動かせない。
// そこで Z軸だけ writeMicroseconds() で直接制御する。
// 角度⇔パルス幅の対応は Servo ライブラリ既定と同じにしてあるので、
// キャリブ値・ホーム位置・押さえ角度の数値はこれまでと変わらない。
const int Z_PULSE_AT_0   = 544;   //   0° 相当のパルス幅 [µs]
const int Z_PULSE_AT_180 = 2400;  // 180° 相当のパルス幅 [µs]
const int Z_PULSE_FLOOR  = 400;   // これより短いパルスは出さない（≒ -14°）
const int Z_PULSE_CEIL   = 2510;  // これより長いパルスは出さない（≒ 190°）

// 最後にZ軸へ指令した角度。zaxis.read() は attach() のパルス幅設定に
// 引きずられて別スケールを返すため、代わりにこの値を参照すること。
int zAngleNow = 0;
// 最後にY軸へ指令した角度（補正前の角度。yaxis.read() は補正後を返すので使わない）
int yAngleNow = 0;

// ===== サーボ個体差の補正（scal コマンド / EEPROM保存）=====
// サーボを替えると同じ角度でも実際の位置がずれるため、軸ごとに2点で直線補正する。
// {a1, b1, a2, b2}: 設定上の角度 a1 を実際には b1 で、a2 を b2 で出す。
// キャリブ値・ホーム位置・押さえ角度などは、すべて補正前の角度のまま使える。
// 既定値 {0, 0, 180, 180} は補正なし（これまでと同じ動き）。
int yCal[4] = {0, 0, 180, 180};
int zCal[4] = {0, 0, 180, 180};

int applyCal(const int* c, int angle) {
  if (c[0] == c[2]) return angle;
  return c[1] + (int)round((float)(angle - c[0]) * (c[3] - c[1]) / (c[2] - c[0]));
}

bool calIsIdentity(const int* c) {
  return c[0] == 0 && c[1] == 0 && c[2] == 180 && c[3] == 180;
}

int zAngleToUs(int angle) {
  long us = Z_PULSE_AT_0 + (long)angle * (Z_PULSE_AT_180 - Z_PULSE_AT_0) / 180;
  if (us < Z_PULSE_FLOOR)   us = Z_PULSE_FLOOR;
  if (us > Z_PULSE_CEIL)    us = Z_PULSE_CEIL;
  return (int)us;
}

// Z軸へ角度で書き込む（リミット判定なし。moveSmooth等の内部用）
void writeZRaw(int angle) {
  zAngleNow = angle;
  zaxis.writeMicroseconds(zAngleToUs(applyCal(zCal, angle)));
}

// Y軸へ角度で書き込む（リミット判定なし。moveSmooth等の内部用）
void writeYRaw(int angle) {
  yAngleNow = angle;
  yaxis.write(applyCal(yCal, angle));
}

// めくり動作の途中の角度（set コマンドで変更・EEPROM保存。サーボ交換時に合わせ直す）
int Z_LIFT   = 160;   // タップでページを捕まえたあと持ち上げるZ角度
int Y_WIGGLE = 8;     // タップ中にYを揺らす幅（Y_HOME から何度下げるか）
int Y_PEEL1  = 80;    // めくるときにYが通る角度（1→2→3 の順）
int Y_PEEL2  = 65;
int Y_PEEL3  = 50;
int Y_PEEL_SPEED = 100; // めくり（Y剥がし）の速さ [%]。100=標準、50=半分の速さ (set ypspeed)

// めくったページを押さえる角度（ページ位置で先頭→最終を線形補間）
int PRESS_START = 168;   // 先頭ページ
int PRESS_END   = 174;   // 最終ページ

// 押さえたまま保持する時間 [ms]
const int PRESS_HOLD_MS = 300;

// キャリブ未設定時の Z 初期値
const int Z_TOUCH_DEFAULT = 43;

int getZHold() {
  float ratio = (float)currentPage / totalPages;
  return (int)(130 + ratio * (145 - 130));  // 130→145度
}

// ページ押さえ角度（ページが進むほど PRESS_START → PRESS_END へ）
int getPressAngle() {
  float ratio = (float)currentPage / totalPages;
  return (int)(PRESS_START + ratio * (PRESS_END - PRESS_START));
}

// ===== 状態 =====
bool isPaused  = true;
bool isStarted = false;
bool stepMode  = false;

// ===== キャリブレーション設定 =====
const int CALIB_INTERVAL     = 50;
const int CALIB_SECTIONS_MAX = 11;   // 550ページ対応
int calibSections = (totalPages / CALIB_INTERVAL) + 1;
int zOffsets[CALIB_SECTIONS_MAX];

void updateCalibSections() {
  calibSections = (totalPages / CALIB_INTERVAL) + 1;
  if (calibSections > CALIB_SECTIONS_MAX) calibSections = CALIB_SECTIONS_MAX;
}

// ===== EEPROMレイアウト =====
const int EEPROM_MAGIC_ADDR     = 0;
const int EEPROM_MAGIC_VAL      = 0xAB;
const int EEPROM_OFFSET_ADDR    = 1;   // 1〜11 (CALIB_SECTIONS_MAX分)
const int EEPROM_PAGES_ADDR     = 15;  // totalPages  (15: magic, 16-17: value)
const int EEPROM_PAGES_MAGIC    = 0xD3;
const int EEPROM_SPEED_ADDR     = 18;  // globalSpeed (18: magic, 19-20: value×100)
const int EEPROM_SPEED_MAGIC    = 0xE5;
const int EEPROM_SETTINGS_ADDR  = 21;  // 可変設定 (21: magic, 22-29: 8値)
// 保存する項目数を変えたらマジックも変えること。
// 旧レイアウトのデータが読み込まれず、新しい既定値が入る。
const int EEPROM_SETTINGS_MAGIC = 0xF3;
const int EEPROM_SCAL_ADDR      = 30;  // サーボ補正 (30: magic, 31-46: yCal・zCal の8値×2byte)
const int EEPROM_SCAL_MAGIC     = 0xC5;
const int EEPROM_MOTION_ADDR    = 47;  // めくり動作の角度 (47: magic, 48-52: 5値)
// 項目数を変えたらマジックも変えること
const int EEPROM_MOTION_MAGIC   = 0xB7;
const int EEPROM_PEELSPD_ADDR   = 53;  // めくりの速さ (53: magic, 54: 値)
const int EEPROM_PEELSPD_MAGIC  = 0xD1;

// ===== 速度設定 =====
float globalSpeed = 1.50;  // 0.1=遅い / 1.0=標準 / 5.0=速い

// ===== 安全書き込み（リミット適用）=====
void writeY(int angle) {
  writeYRaw(constrain(angle, Y_MIN, Y_MAX));
}
void writeZ(int angle) {
  writeZRaw(constrain(angle, Z_MIN, Z_MAX));
}

// ===== 可変設定のEEPROM保存 =====
void saveSettingsToEEPROM() {
  EEPROM.write(EEPROM_SETTINGS_ADDR,     EEPROM_SETTINGS_MAGIC);
  EEPROM.write(EEPROM_SETTINGS_ADDR + 1, (uint8_t)Y_HOME);
  EEPROM.write(EEPROM_SETTINGS_ADDR + 2, (uint8_t)Z_HOME);
  EEPROM.write(EEPROM_SETTINGS_ADDR + 3, (uint8_t)Y_MIN);
  EEPROM.write(EEPROM_SETTINGS_ADDR + 4, (uint8_t)Y_MAX);
  EEPROM.write(EEPROM_SETTINGS_ADDR + 5, (int8_t)Z_MIN);   // 負値あり（符号付き）
  EEPROM.write(EEPROM_SETTINGS_ADDR + 6, (uint8_t)Z_MAX);
  EEPROM.write(EEPROM_SETTINGS_ADDR + 7, (uint8_t)PRESS_START);
  EEPROM.write(EEPROM_SETTINGS_ADDR + 8, (uint8_t)PRESS_END);

  EEPROM.write(EEPROM_MOTION_ADDR,     EEPROM_MOTION_MAGIC);
  EEPROM.write(EEPROM_MOTION_ADDR + 1, (uint8_t)Z_LIFT);
  EEPROM.write(EEPROM_MOTION_ADDR + 2, (uint8_t)Y_WIGGLE);
  EEPROM.write(EEPROM_MOTION_ADDR + 3, (uint8_t)Y_PEEL1);
  EEPROM.write(EEPROM_MOTION_ADDR + 4, (uint8_t)Y_PEEL2);
  EEPROM.write(EEPROM_MOTION_ADDR + 5, (uint8_t)Y_PEEL3);

  EEPROM.write(EEPROM_PEELSPD_ADDR,     EEPROM_PEELSPD_MAGIC);
  EEPROM.write(EEPROM_PEELSPD_ADDR + 1, (uint8_t)Y_PEEL_SPEED);
}

// ===== 可変設定のEEPROM読み込み =====
void loadSettingsFromEEPROM() {
  // めくり動作の角度は別ブロック（後から追加。無ければ既定値のまま）
  if (EEPROM.read(EEPROM_MOTION_ADDR) == EEPROM_MOTION_MAGIC) {
    Z_LIFT   = EEPROM.read(EEPROM_MOTION_ADDR + 1);
    Y_WIGGLE = EEPROM.read(EEPROM_MOTION_ADDR + 2);
    Y_PEEL1  = EEPROM.read(EEPROM_MOTION_ADDR + 3);
    Y_PEEL2  = EEPROM.read(EEPROM_MOTION_ADDR + 4);
    Y_PEEL3  = EEPROM.read(EEPROM_MOTION_ADDR + 5);
  }
  if (EEPROM.read(EEPROM_PEELSPD_ADDR) == EEPROM_PEELSPD_MAGIC) {
    int v = EEPROM.read(EEPROM_PEELSPD_ADDR + 1);
    if (v >= 10) Y_PEEL_SPEED = v;   // 0 だと割り算できないので読み込まない
  }

  if (EEPROM.read(EEPROM_SETTINGS_ADDR) != EEPROM_SETTINGS_MAGIC) return;

  int yh = EEPROM.read(EEPROM_SETTINGS_ADDR + 1);
  int zh = EEPROM.read(EEPROM_SETTINGS_ADDR + 2);
  int yl = EEPROM.read(EEPROM_SETTINGS_ADDR + 3);
  int yu = EEPROM.read(EEPROM_SETTINGS_ADDR + 4);
  int zl = (int8_t)EEPROM.read(EEPROM_SETTINGS_ADDR + 5);  // 負値あり（符号付き）
  int zu = EEPROM.read(EEPROM_SETTINGS_ADDR + 6);
  int ps = EEPROM.read(EEPROM_SETTINGS_ADDR + 7);
  int pe = EEPROM.read(EEPROM_SETTINGS_ADDR + 8);

  // 壊れた値で動かないよう最低限の整合性チェック
  if (yl >= yu || zl >= zu) return;

  Y_HOME = yh;  Z_HOME = zh;
  Y_MIN  = yl;  Y_MAX  = yu;
  Z_MIN  = zl;  Z_MAX  = zu;
  PRESS_START = ps;  PRESS_END = pe;
}

// ===== サーボ補正のEEPROM保存・読み込み =====
void saveServoCalToEEPROM() {
  EEPROM.write(EEPROM_SCAL_ADDR, EEPROM_SCAL_MAGIC);
  for (int i = 0; i < 8; i++) {
    int v = (i < 4) ? yCal[i] : zCal[i - 4];   // 負値あり（符号付き16bit）
    EEPROM.write(EEPROM_SCAL_ADDR + 1 + i * 2, (uint8_t)((uint16_t)v >> 8));
    EEPROM.write(EEPROM_SCAL_ADDR + 2 + i * 2, (uint8_t)((uint16_t)v & 0xFF));
  }
}

void loadServoCalFromEEPROM() {
  if (EEPROM.read(EEPROM_SCAL_ADDR) != EEPROM_SCAL_MAGIC) return;
  int v[8];
  for (int i = 0; i < 8; i++) {
    v[i] = (int16_t)((EEPROM.read(EEPROM_SCAL_ADDR + 1 + i * 2) << 8)
                     | EEPROM.read(EEPROM_SCAL_ADDR + 2 + i * 2));
  }
  // 基準の2点が同じ角度だと直線が決まらないので読み込まない
  if (v[0] == v[2] || v[4] == v[6]) return;
  for (int i = 0; i < 4; i++) { yCal[i] = v[i]; zCal[i] = v[i + 4]; }
}

// ===== サーボ補正の表示（GUIがパースする形式）=====
// [SCAL] y 90>92 50>47  = 設定上の90°を実際は92°、50°を47°で出す
void printServoCal() {
  Serial.print(F("[SCAL] y "));
  Serial.print(yCal[0]); Serial.print('>'); Serial.print(yCal[1]); Serial.print(' ');
  Serial.print(yCal[2]); Serial.print('>'); Serial.println(yCal[3]);
  Serial.print(F("[SCAL] z "));
  Serial.print(zCal[0]); Serial.print('>'); Serial.print(zCal[1]); Serial.print(' ');
  Serial.print(zCal[2]); Serial.print('>'); Serial.println(zCal[3]);
}

// ===== 設定一覧表示（GUIがパースする形式）=====
void printSettings() {
  Serial.println(F("--- Settings ---"));
  Serial.print(F("[SET] yhome=")); Serial.println(Y_HOME);
  Serial.print(F("[SET] zhome=")); Serial.println(Z_HOME);
  Serial.print(F("[SET] ymin="));  Serial.println(Y_MIN);
  Serial.print(F("[SET] ymax="));  Serial.println(Y_MAX);
  Serial.print(F("[SET] zmin="));  Serial.println(Z_MIN);
  Serial.print(F("[SET] zmax="));  Serial.println(Z_MAX);
  Serial.print(F("[SET] pstart=")); Serial.println(PRESS_START);
  Serial.print(F("[SET] pend="));   Serial.println(PRESS_END);
  Serial.print(F("[SET] zlift="));  Serial.println(Z_LIFT);
  Serial.print(F("[SET] ywiggle=")); Serial.println(Y_WIGGLE);
  Serial.print(F("[SET] ypeel1=")); Serial.println(Y_PEEL1);
  Serial.print(F("[SET] ypeel2=")); Serial.println(Y_PEEL2);
  Serial.print(F("[SET] ypeel3=")); Serial.println(Y_PEEL3);
  Serial.print(F("[SET] ypspeed=")); Serial.println(Y_PEEL_SPEED);
  Serial.println(F("----------------"));
}

// ===== 状態ログ =====
void logStatus(const char* state) {
  Serial.print(F("[ "));
  Serial.print(state);
  Serial.print(F(" ]  p."));
  Serial.print(currentPage);
  Serial.print(F(" / "));
  Serial.print(totalPages);
  Serial.print(F("  slot:"));
  Serial.print(getSectionIndex(currentPage));
  Serial.print(F("  Z:"));
  Serial.print(getZTarget());
  Serial.println(F("deg"));
}

// ===== setup =====
void setup() {
  Serial.begin(115200);

  loadSettingsFromEEPROM();
  loadServoCalFromEEPROM();
  loadRewindFromEEPROM();

  yaxis.attach(9);
  // Z軸は 0° 未満・180° 超も使うため、パルス幅の上下限を広げて attach する
  zaxis.attach(10, Z_PULSE_FLOOR, Z_PULSE_CEIL);
  writeY(Y_HOME);
  writeZ(Z_HOME);

  if (EEPROM.read(EEPROM_PAGES_ADDR) == EEPROM_PAGES_MAGIC) {
    int hi = (int)EEPROM.read(EEPROM_PAGES_ADDR + 1);
    int lo = (int)EEPROM.read(EEPROM_PAGES_ADDR + 2);
    int saved = (hi << 8) | lo;
    if (saved >= 10 && saved <= 9999) {
      totalPages = saved;
      updateCalibSections();
    }
  }

  if (EEPROM.read(EEPROM_SPEED_ADDR) == EEPROM_SPEED_MAGIC) {
    int hi = (int)EEPROM.read(EEPROM_SPEED_ADDR + 1);
    int lo = (int)EEPROM.read(EEPROM_SPEED_ADDR + 2);
    int val100 = (hi << 8) | lo;
    float saved = val100 / 100.0;
    if (saved >= 0.1 && saved <= 5.0) globalSpeed = saved;
  }

  for (int i = 0; i < calibSections; i++) zOffsets[i] = Z_TOUCH_DEFAULT;
  loadCalibFromEEPROM();

  if (!calIsIdentity(yCal) || !calIsIdentity(zCal)) {
    Serial.println(F(">> SERVO CAL ON ('scal' で表示)"));
    printServoCal();
  }

  Serial.println(F("=== PAGE TURNER READY ==="));
  Serial.print(F(">> 総ページ数: "));
  Serial.print(totalPages);
  Serial.println(F(" ('pages <num>' で変更可)"));
  Serial.println(F(">> 'help' でコマンド一覧を表示"));
  Serial.println(F(">> 'start' コマンドで開始してください"));
}

// ===== loop =====
void loop() {
  checkSerialInput();

  if (!isStarted || isPaused) {
    delay(100);
    return;
  }

  delay(1500);

  logStatus("TAP");
  tapMotion();
  yMotion();      // 末尾で Y と Z を同時にホームへ戻す
  pressMotion();  // めくったページが浮くので押さえる

  Serial.println(F("------ PAGE DONE ------"));

  currentPage += 2;

  checkSerialInput();  // step off 等を即時反映

  if (stepMode) {
    isPaused = true;
    Serial.println(F(">> STEP: WAITING FOR 'n' / 'next'"));
  }

  if (currentPage >= totalPages) {
    Serial.println(F("=== END OF BOOK ==="));
    isPaused = true;
    goHome();
    // ここで止まったまま。'rewind' で 1 ページ目に戻すか、ページを指定して再開する
  }
}
