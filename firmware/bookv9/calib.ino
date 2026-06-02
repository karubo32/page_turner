// calib.ino — キャリブレーション・EEPROM・補間

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

// ===== キャリブレーション1区間の動作シーケンス =====
void runCalibSequence() {
  logStatus("CAL_TAP");
  tapMotion();
  logStatus("CAL_HAGASI");
  yMotion();
  logStatus("CAL_RETURN");
  moveSmooth(zaxis, getZHold(), Z_HOME, 1.0);
}

// ===== キャリブレーション走行 =====
void runCalibration() {
  Serial.println(F("=== CALIBRATION MODE ==="));
  Serial.println(F("Enter: 動作確認 / 数値: offset設定 / t: 設定値で試行 / h: 再試行 / s: スキップ"));

  for (int i = 0; i < calibSections; i++) {
    int secPage = i * CALIB_INTERVAL;
    if (secPage >= totalPages) break;

    currentPage = secPage;

    Serial.print(F("[SEC "));
    Serial.print(i);
    Serial.print(F("] page="));
    Serial.print(secPage);
    Serial.print(F(" 現在Z="));
    Serial.print(getZTarget());
    Serial.println(F(" | Enter: 動作確認 / s: スキップ"));

    while (!Serial.available()) delay(50);
    char input[16];
    readSerialLine(input, sizeof(input));

    if (input[0] == 's' || input[0] == 'S') {
      Serial.println(F("SKIP"));
      continue;
    }

    Serial.println(F(">> 動作確認中..."));
    runCalibSequence();

    Serial.println(F("  数値: offset設定 / t: 再試行 / h: offset0で試行 / ok: 確定 / s: スキップ"));
    while (true) {
      Serial.print(F("  > "));
      while (!Serial.available()) delay(50);

      char input2[16];
      readSerialLine(input2, sizeof(input2));

      if (input2[0] == 'h' || input2[0] == 'H') {
        goHome();
        Serial.println(F(">> 再試行..."));
        runCalibSequence();
        Serial.println(F("  数値: offset設定 / t: 設定値で試行 / h: 再試行 / ok: 確定 / s: スキップ"));
        continue;
      }

      if (input2[0] == 't' || input2[0] == 'T') {
        Serial.print(F(">> 試行 Z="));
        Serial.println(getZTarget());
        goHome();
        runCalibSequence();
        Serial.println(F("  数値: offset設定 / t: 再試行 / h: offset0で試行 / s: スキップ"));
        continue;
      }

      if (input2[0] == 's' || input2[0] == 'S') {
        Serial.println(F("SKIP"));
        break;
      }

      int actual = atoi(input2);
      if (actual > 0) {
        zOffsets[i] = actual;
        Serial.print(F(">> Z="));
        Serial.print(zOffsets[i]);
        Serial.print(F(" (次タップ予測: "));
        Serial.print(getZTarget());
        Serial.println(F(")"));
        Serial.println(F("  't' で試行 / 別の数値で再設定 / 's' でスキップ / 'ok' で確定"));
        continue;
      }

      if (strcmp(input2, "ok") == 0) {
        Serial.print(F(">> 確定 Z="));
        Serial.println(zOffsets[i]);
        break;
      }

      Serial.println(F("  無効。数値 / t / h / s / ok を入力"));
    }
  }

  saveCalibToEEPROM();
  printOffsetTable();
  Serial.println(F("=== CALIBRATION DONE ==="));
  Serial.println(F(">> 'start' で動作開始"));
  isCalibMode = false;
  currentPage = 0;
  goHome();
}
