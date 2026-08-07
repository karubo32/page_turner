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

int   getSectionIndex(int page);
float getInterpolatedZ(int page);
int   getZTarget();
void  saveCalibToEEPROM();
bool  loadCalibFromEEPROM();
void  printOffsetTable();

int   readSerialLine(char* buf, int bufSize);
void  checkSerialInput();

// ===== 本情報 =====
int totalPages  = 180;    // pages コマンドで変更可能
int currentPage = 1;

// ===== 可変設定（set コマンド / GUIの詳細設定から変更・EEPROM保存）=====
int Y_HOME = 90;    // Y軸待機位置
int Z_HOME = 90;    // Z軸待機位置
int Y_MIN  = 45;    // Y軸リミット（下限）
int Y_MAX  = 210;   // Y軸リミット（上限）
int Z_MIN  = 1;    // Z軸リミット（下限）
int Z_MAX  = 160;   // Z軸リミット（上限）

// キャリブ未設定時の Z 初期値
const int Z_TOUCH_DEFAULT = 43;

int getZHold() {
  float ratio = (float)currentPage / totalPages;
  return (int)(130 + ratio * (145 - 130));  // 130→145度
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
const int EEPROM_SETTINGS_ADDR  = 21;  // 可変設定 (21: magic, 22-27: 6値)
const int EEPROM_SETTINGS_MAGIC = 0xF1;

// ===== 速度設定 =====
float globalSpeed = 1.50;  // 0.1=遅い / 1.0=標準 / 5.0=速い

// ===== 安全書き込み（リミット適用）=====
void writeY(int angle) {
  yaxis.write(constrain(angle, Y_MIN, Y_MAX));
}
void writeZ(int angle) {
  zaxis.write(constrain(angle, Z_MIN, Z_MAX));
}

// ===== 可変設定のEEPROM保存 =====
void saveSettingsToEEPROM() {
  EEPROM.write(EEPROM_SETTINGS_ADDR,     EEPROM_SETTINGS_MAGIC);
  EEPROM.write(EEPROM_SETTINGS_ADDR + 1, (uint8_t)Y_HOME);
  EEPROM.write(EEPROM_SETTINGS_ADDR + 2, (uint8_t)Z_HOME);
  EEPROM.write(EEPROM_SETTINGS_ADDR + 3, (uint8_t)Y_MIN);
  EEPROM.write(EEPROM_SETTINGS_ADDR + 4, (uint8_t)Y_MAX);
  EEPROM.write(EEPROM_SETTINGS_ADDR + 5, (uint8_t)Z_MIN);
  EEPROM.write(EEPROM_SETTINGS_ADDR + 6, (uint8_t)Z_MAX);
}

// ===== 可変設定のEEPROM読み込み =====
void loadSettingsFromEEPROM() {
  if (EEPROM.read(EEPROM_SETTINGS_ADDR) != EEPROM_SETTINGS_MAGIC) return;

  int yh = EEPROM.read(EEPROM_SETTINGS_ADDR + 1);
  int zh = EEPROM.read(EEPROM_SETTINGS_ADDR + 2);
  int yl = EEPROM.read(EEPROM_SETTINGS_ADDR + 3);
  int yu = EEPROM.read(EEPROM_SETTINGS_ADDR + 4);
  int zl = EEPROM.read(EEPROM_SETTINGS_ADDR + 5);
  int zu = EEPROM.read(EEPROM_SETTINGS_ADDR + 6);

  // 壊れた値で動かないよう最低限の整合性チェック
  if (yl >= yu || zl >= zu) return;

  Y_HOME = yh;  Z_HOME = zh;
  Y_MIN  = yl;  Y_MAX  = yu;
  Z_MIN  = zl;  Z_MAX  = zu;
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

  for (int i = 0; i < calibSections; i++) zOffsets[i] = Z_TOUCH_DEFAULT;
  loadCalibFromEEPROM();

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
  yMotion();   // 末尾で Y と Z を同時にホームへ戻す

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
    while (1) checkSerialInput();
  }
}
