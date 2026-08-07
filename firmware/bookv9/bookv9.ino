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
void  goHome();
void  tapMotion();
void  yMotion();
void  wiperMotion();

int   getSectionIndex(int page);
float getInterpolatedZ(int page);
int   getZTarget();
void  saveCalibToEEPROM();
bool  loadCalibFromEEPROM();
void  printOffsetTable();
void  runCalibSequence();
void  runCalibration();

int   readSerialLine(char* buf, int bufSize);
void  checkSerialInput();

void  saveTestrunState();
void  clearTestrunState();
void  runTestrun();

// ===== 本情報 =====
int totalPages  = 180;    // pages コマンドで変更可能
int currentPage = 1;

// ===== 待機位置 =====
const int Y_HOME = 90;
const int Z_HOME = 90;

// ===== Z軸設定 =====
const int Z_TOUCH_MIN = 43;
const int Z_TOUCH_MAX = 29;

int getZHold() {
  float ratio = (float)currentPage / totalPages;
  return (int)(130 + ratio * (145 - 130));  // 130→145度
}

// ===== 状態 =====
bool isPaused   = true;
bool isStarted  = false;
int  direction  = 1;

// ===== キャリブレーション設定 =====
const int CALIB_INTERVAL     = 50;
const int CALIB_SECTIONS_MAX = 11;   // 550ページ対応
int calibSections = (totalPages / CALIB_INTERVAL) + 1;
int zOffsets[CALIB_SECTIONS_MAX];

void updateCalibSections() {
  calibSections = (totalPages / CALIB_INTERVAL) + 1;
  if (calibSections > CALIB_SECTIONS_MAX) calibSections = CALIB_SECTIONS_MAX;
}

bool isCalibMode = false;
bool stepMode    = false;
bool isTestrun   = false;
int  testrunPage = 1;

// ===== EEPROMレイアウト =====
const int EEPROM_MAGIC_ADDR    = 0;
const int EEPROM_MAGIC_VAL     = 0xAB;
const int EEPROM_OFFSET_ADDR   = 1;   // 1〜11 (CALIB_SECTIONS_MAX分)
const int EEPROM_TESTRUN_ADDR  = 12;  // testrunモード保存
const int EEPROM_TESTRUN_MAGIC = 0xC7;
const int EEPROM_PAGES_ADDR    = 15;  // totalPages保存 (15: magic, 16-17: value)
const int EEPROM_PAGES_MAGIC   = 0xD3;
const int EEPROM_SPEED_ADDR    = 18;  // globalSpeed保存 (18: magic, 19-20: value×100)
const int EEPROM_SPEED_MAGIC   = 0xE5;

// ===== サーボ角度リミット（全動作共通・物理角度で適用）=====
const int Y_MIN = 45;
const int Y_MAX = 210;
const int Z_MIN = 20;
const int Z_MAX = 160;

// ===== 速度設定 =====
float globalSpeed = 1.50;  // 0.1=遅い / 1.0=標準 / 5.0=速い

// ===== ワイパー設定 =====
const int WIPER_INTERVAL = 1000;
int wipeCount = 0;

const int wy1 = 123;  // 1手前
const int wy2 = 129;  // 1奥
const int wy3 = 143;  // 2手前
const int wy4 = 138;  // 2奥
const int wy5 = 126;  // 1center
const int wz1 = 30;   // 上
const int wz2 = 24;   // 下

// ===== 角度反転 =====
int applyDirection(int angle) {
  if (direction == 1) return angle;
  return 180 - angle;
}

// ===== 安全書き込み（applyDirection + リミット適用）=====
void writeY(int logicalAngle) {
  yaxis.write(constrain(applyDirection(logicalAngle), Y_MIN, Y_MAX));
}
void writeZ(int logicalAngle) {
  zaxis.write(constrain(applyDirection(logicalAngle), Z_MIN, Z_MAX));
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
  Serial.print(F("deg  dir:"));
  Serial.println(direction == 1 ? F(">>") : F("<<"));
}

// ===== setup =====
void setup() {
  Serial.begin(115200);

  yaxis.attach(9);
  zaxis.attach(10);
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

  for (int i = 0; i < calibSections; i++) zOffsets[i] = Z_TOUCH_MIN;
  loadCalibFromEEPROM();

  if (EEPROM.read(EEPROM_TESTRUN_ADDR) == EEPROM_TESTRUN_MAGIC) {
    int hi = (int)EEPROM.read(EEPROM_TESTRUN_ADDR + 1);
    int lo = (int)EEPROM.read(EEPROM_TESTRUN_ADDR + 2);
    testrunPage = (hi << 8) | lo;
    if (testrunPage < 1 || testrunPage >= totalPages) testrunPage = 1;
    isTestrun = true;
    Serial.println(F("=== TESTRUN MODE (resumed) ==="));
    Serial.print(F(">> 再開ページ: "));
    Serial.println(testrunPage);
    Serial.println(F(">> 'testrun stop' で終了"));
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
  if (isCalibMode) {
    runCalibration();
    return;
  }

  if (isTestrun) {
    runTestrun();
    return;
  }

  checkSerialInput();

  if (!isStarted || isPaused) {
    delay(100);
    return;
  }

  delay(1500);

  wipeCount++;
  if (wipeCount >= WIPER_INTERVAL) {
    wipeCount = 0;
    wiperMotion();
  }

  logStatus("TAP");
  tapMotion();
  yMotion();
  moveSmooth(zaxis, getZHold(), Z_HOME);

  Serial.println(F("------ PAGE DONE ------"));

  currentPage += direction * 2;

  checkSerialInput();  // step off 等を即時反映

  if (stepMode) {
    isPaused = true;
    Serial.println(F(">> STEP: WAITING FOR 'n' / 'next'"));
  }

  if (currentPage <= 0 || currentPage >= totalPages) {
    Serial.println(F("=== END OF BOOK ==="));
    isPaused = true;
    goHome();
    while (1) checkSerialInput();
  }
}
