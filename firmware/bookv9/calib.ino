// calib.ino — キャリブレーションテーブル・EEPROM・補間
//
// 区間ごとのZ絶対角度は GUI のキャリブレーションテーブル（oz コマンド）から
// 設定する。対話式のキャリブレーション走行は廃止した。

// ===== 区間インデックス =====
int getSectionIndex(int page) {
  return constrain(page / CALIB_INTERVAL, 0, calibSections - 1);
}

// ===== スロット間の線形補間でZ絶対角度を取得 =====
float getInterpolatedZ(int page) {
  int idx  = getSectionIndex(page);
  int next = idx + 1;
  if (next >= calibSections) return zOffsets[idx];
  float t = (float)(page % CALIB_INTERVAL) / CALIB_INTERVAL;
  return zOffsets[idx] * (1.0 - t) + zOffsets[next] * t;
}

// ===== Z目標（テーブル補間のみ）=====
int getZTarget() {
  return (int)round(getInterpolatedZ(currentPage));
}

// ===== EEPROM保存 =====
void saveCalibToEEPROM() {
  EEPROM.write(EEPROM_MAGIC_ADDR, EEPROM_MAGIC_VAL);
  for (int i = 0; i < calibSections; i++) {
    EEPROM.write(EEPROM_OFFSET_ADDR + i, (int8_t)zOffsets[i]);
  }
  Serial.println(F(">> EEPROM SAVED"));
}

// ===== EEPROM読み込み =====
bool loadCalibFromEEPROM() {
  if (EEPROM.read(EEPROM_MAGIC_ADDR) != EEPROM_MAGIC_VAL) {
    Serial.println(F(">> NO CALIB DATA"));
    return false;
  }
  for (int i = 0; i < calibSections; i++) {
    zOffsets[i] = (int8_t)EEPROM.read(EEPROM_OFFSET_ADDR + i);
  }
  Serial.println(F(">> CALIB LOADED"));
  printOffsetTable();
  return true;
}

// ===== オフセットテーブル表示 =====
void printOffsetTable() {
  Serial.println(F("--- Offset Table ---"));
  for (int i = 0; i < calibSections; i++) {
    int startPage = i * CALIB_INTERVAL;
    if (startPage >= totalPages) break;

    Serial.print(F("  ["));
    Serial.print(i);
    Serial.print(F("] page "));
    Serial.print(startPage);
    Serial.print(F("~: Z="));
    Serial.println(zOffsets[i]);
  }
  Serial.println(F("--------------------"));
}
