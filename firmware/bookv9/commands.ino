// commands.ino — シリアルコマンドパーサー

// ===== シリアル入力読み取り =====
int readSerialLine(char* buf, int bufSize) {
  int len = Serial.readBytesUntil('\n', buf, bufSize - 1);
  buf[len] = '\0';
  while (len > 0 && (buf[len - 1] == '\r' || buf[len - 1] == ' ')) {
    buf[--len] = '\0';
  }
  return len;
}

// ===== コマンド処理 =====
void checkSerialInput() {
  if (!Serial.available()) return;

  char cmd[32];
  readSerialLine(cmd, sizeof(cmd));
  for (int i = 0; cmd[i]; i++) cmd[i] = tolower((unsigned char)cmd[i]);

  // === help ===
  if (strcmp(cmd, "help") == 0 || strcmp(cmd, "h") == 0 || strcmp(cmd, "?") == 0) {
    Serial.println(F("========== HELP =========="));
    Serial.println(F("--- 基本操作 ---"));
    Serial.println(F("  start / s        : 動作開始"));
    Serial.println(F("  stop / pause / p : 一時停止"));
    Serial.println(F("  resume / r       : 再開"));
    Serial.println(F("  f / forward      : 順方向"));
    Serial.println(F("  b / back         : 逆方向"));
    Serial.println(F("  <ページ番号>     : ページジャンプ（例: 150）"));
    Serial.println(F("--- 1ページモード ---"));
    Serial.println(F("  step             : 1ページモード ON/OFF"));
    Serial.println(F("  n / next         : 1ページ進む（stepモード時）"));
    Serial.println(F("--- 速度 ---"));
    Serial.println(F("  speed <val>      : 速度変更 0.1~5.0（標準:1.0）"));
    Serial.println(F("--- サーボ手動操作（停止中のみ）---"));
    Serial.println(F("  z <angle>        : Z軸を指定角度へ"));
    Serial.println(F("  y <angle>        : Y軸を指定角度へ"));
    Serial.println(F("  z+ / z-          : Z軸を1度ずつ移動"));
    Serial.println(F("  y+ / y-          : Y軸を1度ずつ移動"));
    Serial.println(F("  home             : ホームへ戻る"));
    Serial.println(F("--- メンテナンス ---"));
    Serial.println(F("  wiper            : ふきふき動作を実行"));
    Serial.println(F("--- キャリブレーション ---"));
    Serial.println(F("  calib            : キャリブレーション開始"));
    Serial.println(F("  calib_reset      : キャリブデータ消去"));
    Serial.println(F("  table            : オフセット一覧表示"));
    Serial.println(F("  oz <slot> <val>  : Z補正（例: oz 5 43）"));
    Serial.println(F("--- テスト ---"));
    Serial.println(F("  test <page>      : 指定ページのZ値でタップ1回"));
    Serial.println(F("  testrun          : p.1から全ページ順にタップ(EEPROM保存)"));
    Serial.println(F("  testrun stop     : testrunモード終了"));
    Serial.println(F("--- 本の設定 ---"));
    Serial.println(F("  pages <num>      : 総ページ数変更 例: pages 320"));
    Serial.println(F("  pages            : 現在の総ページ数を表示"));
    Serial.println(F("--- その他 ---"));
    Serial.println(F("  help / h / ?     : このヘルプ"));
    Serial.println(F("=========================="));
    return;
  }

  // === start ===
  if (strcmp(cmd, "start") == 0 || strcmp(cmd, "s") == 0) {
    if (!isStarted) {
      isStarted = true;
      isPaused  = false;
      Serial.println(F(">> STARTED"));
    } else {
      isPaused = false;
      Serial.println(F(">> RESUMED"));
    }
    return;
  }

  // === pause / stop ===
  if (strcmp(cmd, "p") == 0 || strcmp(cmd, "pause") == 0 || strcmp(cmd, "stop") == 0) {
    isPaused = true;
    stepMode = false;
    if (isTestrun) {
      isTestrun   = false;
      testrunPage = 1;
      clearTestrunState();
      Serial.println(F(">> TESTRUN STOPPED"));
    }
    Serial.println(F(">> PAUSED"));
    return;
  }

  // === resume ===
  if (strcmp(cmd, "r") == 0 || strcmp(cmd, "resume") == 0) {
    if (isStarted) {
      isPaused = false;
      Serial.println(F(">> RESUMED"));
    } else {
      Serial.println(F(">> Not started. Send 'start' first."));
    }
    return;
  }

  // === 方向 ===
  if (strcmp(cmd, "f") == 0 || strcmp(cmd, "forward") == 0) {
    direction = 1;
    Serial.println(F(">> DIRECTION: FORWARD"));
    return;
  }
  if (strcmp(cmd, "b") == 0 || strcmp(cmd, "back") == 0 || strcmp(cmd, "reverse") == 0) {
    direction = -1;
    Serial.println(F(">> DIRECTION: REVERSE"));
    return;
  }

  // === wiper ===
  if (strcmp(cmd, "wiper") == 0) {
    isPaused = true;
    wiperMotion();
    return;
  }

  // === home ===
  if (strcmp(cmd, "home") == 0) {
    isPaused = true;
    goHome();
    return;
  }

  // === t / tap ===
  if (strcmp(cmd, "t") == 0 || strcmp(cmd, "tap") == 0) {
    bool wasRunning = !isPaused;
    isPaused = true;
    Serial.print(F(">> TAP TEST  Z:"));
    Serial.println(getZTarget());
    tapMotion();
    isPaused = !wasRunning;
    return;
  }

  // === z <angle> ===
  if (strncmp(cmd, "z ", 2) == 0 && cmd[2] != '+' && cmd[2] != '-') {
    if (isPaused) {
      int req      = atoi(cmd + 2);
      int physical = applyDirection(req);
      int clamped  = constrain(physical, Z_MIN, Z_MAX);
      zaxis.write(clamped);
      Serial.print(F(">> Z -> "));
      Serial.print(req);
      if (clamped != physical) Serial.print(F(" [LIMIT]"));
      Serial.println();
    } else {
      Serial.println(F(">> 一時停止中のみ使用可"));
    }
    return;
  }

  // === y <angle> ===
  if (strncmp(cmd, "y ", 2) == 0 && cmd[2] != '+' && cmd[2] != '-') {
    if (isPaused) {
      int req      = atoi(cmd + 2);
      int physical = applyDirection(req);
      int clamped  = constrain(physical, Y_MIN, Y_MAX);
      yaxis.write(clamped);
      Serial.print(F(">> Y -> "));
      Serial.print(req);
      if (clamped != physical) Serial.print(F(" [LIMIT]"));
      Serial.println();
    } else {
      Serial.println(F(">> 一時停止中のみ使用可"));
    }
    return;
  }

  // === z+ / z- ===
  if (strcmp(cmd, "z+") == 0 || strcmp(cmd, "z-") == 0) {
    if (isPaused) {
      int next = constrain(zaxis.read() + (cmd[1] == '+' ? 1 : -1), Z_MIN, Z_MAX);
      zaxis.write(next);
      Serial.print(F(">> Z -> "));
      Serial.println(next);
    } else {
      Serial.println(F(">> 一時停止中のみ使用可"));
    }
    return;
  }

  // === y+ / y- ===
  if (strcmp(cmd, "y+") == 0 || strcmp(cmd, "y-") == 0) {
    if (isPaused) {
      int next = constrain(yaxis.read() + (cmd[1] == '+' ? 1 : -1), Y_MIN, Y_MAX);
      yaxis.write(next);
      Serial.print(F(">> Y -> "));
      Serial.println(next);
    } else {
      Serial.println(F(">> 一時停止中のみ使用可"));
    }
    return;
  }

  // === step ===
  if (strcmp(cmd, "step") == 0) {
    stepMode = !stepMode;
    Serial.print(F(">> STEP MODE: "));
    Serial.println(stepMode ? F("ON") : F("OFF"));
    return;
  }
  if (strcmp(cmd, "step on") == 0) {
    stepMode = true;
    Serial.println(F(">> STEP MODE: ON"));
    return;
  }
  if (strcmp(cmd, "step off") == 0) {
    stepMode = false;
    Serial.println(F(">> STEP MODE: OFF"));
    return;
  }

  // === n / next ===
  if (strcmp(cmd, "n") == 0 || strcmp(cmd, "next") == 0) {
    if (stepMode) {
      isPaused = false;
      Serial.println(F(">> NEXT PAGE"));
    } else {
      Serial.println(F(">> STEP MODE OFF. 'step' で有効化"));
    }
    return;
  }

  // === calib ===
  if (strcmp(cmd, "calib") == 0) {
    isPaused    = true;
    isCalibMode = true;
    return;
  }

  // === calib_reset ===
  if (strcmp(cmd, "calib_reset") == 0) {
    for (int i = 0; i < calibSections; i++) zOffsets[i] = Z_TOUCH_MIN;
    EEPROM.write(EEPROM_MAGIC_ADDR, 0x00);
    Serial.println(F(">> CALIB RESET"));
    return;
  }

  // === table ===
  if (strcmp(cmd, "table") == 0) {
    printOffsetTable();
    return;
  }

  // === oz <slot> <angle> ===
  if (strncmp(cmd, "oz ", 3) == 0) {
    int slot = -1, angle = 0;
    if (sscanf(cmd + 3, "%d %d", &slot, &angle) == 2) {
      if (slot >= 0 && slot < calibSections) {
        zOffsets[slot] = angle;
        saveCalibToEEPROM();
        Serial.print(F(">> [REALTIME] Slot "));
        Serial.print(slot);
        Serial.print(F(" Z="));
        Serial.print(zOffsets[slot]);
        Serial.print(F("  (次タップのZ予測: "));
        Serial.print(getZTarget());
        Serial.println(F(")"));
      } else {
        Serial.print(F(">> INVALID SLOT (0~"));
        Serial.print(calibSections - 1);
        Serial.println(F(")"));
      }
    } else {
      Serial.println(F(">> 書式: oz <slot> <angle>  例: oz 3 44"));
    }
    return;
  }

  // === speed <val> ===
  if (strncmp(cmd, "speed ", 6) == 0) {
    float val = atof(cmd + 6);
    if (val >= 0.1 && val <= 5.0) {
      globalSpeed = val;
      int val100 = (int)(globalSpeed * 100);
      EEPROM.write(EEPROM_SPEED_ADDR,     EEPROM_SPEED_MAGIC);
      EEPROM.write(EEPROM_SPEED_ADDR + 1, (uint8_t)(val100 >> 8));
      EEPROM.write(EEPROM_SPEED_ADDR + 2, (uint8_t)(val100 & 0xFF));
      Serial.print(F(">> SPEED: "));
      Serial.println(globalSpeed);
    } else {
      Serial.println(F(">> 範囲外です (0.1〜5.0)"));
    }
    return;
  }

  // === pages ===
  if (strcmp(cmd, "pages") == 0) {
    Serial.print(F(">> TOTAL PAGES: "));
    Serial.println(totalPages);
    return;
  }
  if (strncmp(cmd, "pages ", 6) == 0) {
    int newPages = atoi(cmd + 6);
    if (newPages >= 10 && newPages <= 9999) {
      totalPages = newPages;
      updateCalibSections();
      if (currentPage >= totalPages) currentPage = 1;
      EEPROM.write(EEPROM_PAGES_ADDR,     EEPROM_PAGES_MAGIC);
      EEPROM.write(EEPROM_PAGES_ADDR + 1, (uint8_t)(totalPages >> 8));
      EEPROM.write(EEPROM_PAGES_ADDR + 2, (uint8_t)(totalPages & 0xFF));
      Serial.print(F(">> TOTAL PAGES SET: "));
      Serial.print(totalPages);
      Serial.print(F("  (sections: "));
      Serial.print(calibSections);
      Serial.println(F(")"));
    } else {
      Serial.println(F(">> 範囲外です (10〜9999)"));
    }
    return;
  }

  // === test <page> ===
  if (strncmp(cmd, "test ", 5) == 0 && cmd[5] != 'r') {
    int testPage = atoi(cmd + 5);
    if (testPage >= 0 && testPage < totalPages) {
      int savedPage = currentPage;
      currentPage   = testPage;
      Serial.print(F(">> TEST p."));
      Serial.print(testPage);
      Serial.print(F("  Z:"));
      Serial.print(getZTarget());
      Serial.println(F("deg"));
      logStatus("TEST");
      tapMotion();
      yMotion();
      moveSmooth(zaxis, getZHold(), Z_HOME);
      currentPage = savedPage;
    } else {
      Serial.println(F(">> ページ範囲外"));
    }
    return;
  }

  // === testrun stop ===
  if (strcmp(cmd, "testrun stop") == 0) {
    isTestrun   = false;
    testrunPage = 1;
    clearTestrunState();
    goHome();
    Serial.println(F(">> TESTRUN STOPPED"));
    return;
  }

  // === testrun ===
  if (strcmp(cmd, "testrun") == 0) {
    isTestrun   = true;
    testrunPage = 1;
    saveTestrunState();
    Serial.println(F("=== TESTRUN MODE START ==="));
    Serial.print(F(">> 総ページ数: "));
    Serial.println(totalPages);
    Serial.println(F(">> p.1 から順番にタップします"));
    Serial.println(F(">> 'testrun stop' で終了"));
    return;
  }

  // === ページジャンプ ===
  int page = atoi(cmd);
  if (page > 0 && page < totalPages) {
    if (page % 2 == 0) page++;  // 奇数に丸める
    currentPage = constrain(page, 1, totalPages - 1);
    Serial.print(F(">> PAGE SET: "));
    Serial.println(currentPage);
    return;
  }

  Serial.println(F(">> INVALID COMMAND"));
}
