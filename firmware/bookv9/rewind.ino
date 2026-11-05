// rewind.ino — 1ページ目に戻る動作（ハンドでページを引っ掛けて一気に戻す）
//
// 動きは「段」の並びで、各段で Y・Z を指定角度へ同時に動かし、指定時間待つ。
// 角度・速さ・待ち時間・段数はすべて rw コマンドで設定し、EEPROM に保存する。
//
//   rewind                 : 戻す動作を実行 → ホームへ戻り、ページを 1 にする
//   rw                     : 設定の一覧（[RW] 形式。GUIがパースする）
//   rw <段> <Y> <Z> <速さ> <待ちms> : 段を設定（段は 0〜7）
//   rw n <段数>            : 使う段数（0〜8。0 なら動かずにページだけ 1 に戻す）
//   rw go <段>             : その段の位置へだけ動かす（一時停止中のみ。調整用）
//
// 速さ: 10 = 標準、大きいほど速い（1〜100）。0 = なめらか移動なしで一気に指令する

const int RW_STEPS_MAX       = 8;
const int EEPROM_RW_ADDR     = 55;   // 55: magic, 56: 段数, 57〜: 1段 6byte (Y 2, Z 2, 速さ 1, 待ち/10 1)
const int EEPROM_RW_MAGIC    = 0xE2;
const int RW_STEP_BYTES      = 6;

int rwCount = 0;
int rwY[RW_STEPS_MAX];
int rwZ[RW_STEPS_MAX];
int rwSpeed[RW_STEPS_MAX];
int rwWait[RW_STEPS_MAX];   // ms

void rwDefaults() {
  rwCount = 0;
  for (int i = 0; i < RW_STEPS_MAX; i++) {
    rwY[i] = Y_HOME; rwZ[i] = Z_HOME; rwSpeed[i] = 10; rwWait[i] = 0;
  }
}

static void eepromWrite16(int addr, int v) {
  EEPROM.write(addr,     (uint8_t)((uint16_t)v >> 8));
  EEPROM.write(addr + 1, (uint8_t)((uint16_t)v & 0xFF));
}
static int eepromRead16(int addr) {
  return (int16_t)((EEPROM.read(addr) << 8) | EEPROM.read(addr + 1));
}

void saveRewindToEEPROM() {
  EEPROM.write(EEPROM_RW_ADDR,     EEPROM_RW_MAGIC);
  EEPROM.write(EEPROM_RW_ADDR + 1, (uint8_t)rwCount);
  for (int i = 0; i < RW_STEPS_MAX; i++) {
    int a = EEPROM_RW_ADDR + 2 + i * RW_STEP_BYTES;
    eepromWrite16(a,     rwY[i]);
    eepromWrite16(a + 2, rwZ[i]);
    EEPROM.write(a + 4, (uint8_t)rwSpeed[i]);
    EEPROM.write(a + 5, (uint8_t)(rwWait[i] / 10));
  }
}

void loadRewindFromEEPROM() {
  rwDefaults();
  if (EEPROM.read(EEPROM_RW_ADDR) != EEPROM_RW_MAGIC) return;
  int n = EEPROM.read(EEPROM_RW_ADDR + 1);
  if (n > RW_STEPS_MAX) return;
  rwCount = n;
  for (int i = 0; i < RW_STEPS_MAX; i++) {
    int a = EEPROM_RW_ADDR + 2 + i * RW_STEP_BYTES;
    rwY[i]     = eepromRead16(a);
    rwZ[i]     = eepromRead16(a + 2);
    rwSpeed[i] = EEPROM.read(a + 4);
    rwWait[i]  = EEPROM.read(a + 5) * 10;
  }
}

// [RW] n=3 / [RW] 0 y=90 z=120 s=10 w=200
void printRewind() {
  Serial.print(F("[RW] n=")); Serial.println(rwCount);
  for (int i = 0; i < RW_STEPS_MAX; i++) {
    Serial.print(F("[RW] ")); Serial.print(i);
    Serial.print(F(" y=")); Serial.print(rwY[i]);
    Serial.print(F(" z=")); Serial.print(rwZ[i]);
    Serial.print(F(" s=")); Serial.print(rwSpeed[i]);
    Serial.print(F(" w=")); Serial.println(rwWait[i]);
  }
}

// 1段ぶん動かす（リミットは moveSmoothDual / writeY / writeZ がかける）
void rwMoveStep(int i) {
  if (rwSpeed[i] == 0) {
    writeY(rwY[i]);
    writeZ(rwZ[i]);
  } else {
    moveSmoothDual(yAngleNow, rwY[i], zAngleNow, rwZ[i], 10.0 / rwSpeed[i]);
  }
}

void runRewind() {
  bool wasRunning = isStarted && !isPaused;
  isPaused = true;
  if (wasRunning) Serial.println(F(">> PAUSED"));

  if (rwCount == 0) {
    Serial.println(F(">> REWIND: 動作が未設定のため、ページだけ 1 に戻します ('rw' で設定)"));
  } else {
    Serial.println(F(">> REWIND START"));
    for (int i = 0; i < rwCount; i++) {
      Serial.print(F(">> RW STEP ")); Serial.println(i);
      rwMoveStep(i);
      if (rwWait[i] > 0) delay(rwWait[i]);
    }
    goHome();
  }
  currentPage = 1;
  Serial.println(F(">> REWIND DONE"));
  logStatus("REWIND");
}

// rewind / rw 系コマンドなら処理して true
bool handleRewindCommand(const char* cmd) {
  if (strcmp(cmd, "rewind") == 0) {
    runRewind();
    return true;
  }
  if (strcmp(cmd, "rw") == 0) {
    printRewind();
    return true;
  }
  if (strncmp(cmd, "rw n ", 5) == 0) {
    int n = atoi(cmd + 5);
    if (n < 0 || n > RW_STEPS_MAX) {
      Serial.println(F(">> 段数は 0〜8"));
      return true;
    }
    rwCount = n;
    saveRewindToEEPROM();
    printRewind();
    return true;
  }
  if (strncmp(cmd, "rw go ", 6) == 0) {
    int i = atoi(cmd + 6);
    if (i < 0 || i >= RW_STEPS_MAX) {
      Serial.println(F(">> 段は 0〜7"));
    } else if (!isPaused) {
      Serial.println(F(">> 一時停止中のみ使用可"));
    } else {
      rwMoveStep(i);
      Serial.print(F(">> Y -> ")); Serial.println(yAngleNow);
      Serial.print(F(">> Z -> ")); Serial.println(zAngleNow);
    }
    return true;
  }
  if (strncmp(cmd, "rw ", 3) == 0) {
    int i, y, z, s, w;
    if (sscanf(cmd + 3, "%d %d %d %d %d", &i, &y, &z, &s, &w) != 5) {
      Serial.println(F(">> 書式: rw <段> <Y> <Z> <速さ> <待ちms>  例: rw 0 90 120 10 200"));
      return true;
    }
    if (i < 0 || i >= RW_STEPS_MAX || s < 0 || s > 100 || w < 0 || w > 2550) {
      Serial.println(F(">> 範囲外 (段 0〜7 / 速さ 0〜100 / 待ち 0〜2550ms)"));
      return true;
    }
    rwY[i] = constrain(y, Y_MIN, Y_MAX);
    rwZ[i] = constrain(z, Z_MIN, Z_MAX);
    rwSpeed[i] = s;
    rwWait[i] = w;
    saveRewindToEEPROM();
    printRewind();
    return true;
  }
  return false;
}
