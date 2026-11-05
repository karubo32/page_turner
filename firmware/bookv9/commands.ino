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

// ===== set コマンドの1項目を適用 =====
// 戻り値: true=適用した / false=名前が不正
bool applySetting(const char* name, int val) {
  if      (strcmp(name, "yhome")  == 0) Y_HOME      = val;
  else if (strcmp(name, "zhome")  == 0) Z_HOME      = val;
  else if (strcmp(name, "ybase")  == 0) Y_BASE      = val;
  else if (strcmp(name, "zbase")  == 0) Z_BASE      = val;
  else if (strcmp(name, "ymin")   == 0) Y_MIN       = val;
  else if (strcmp(name, "ymax")   == 0) Y_MAX       = val;
  else if (strcmp(name, "zmin")   == 0) Z_MIN       = val;
  else if (strcmp(name, "zmax")   == 0) Z_MAX       = val;
  else if (strcmp(name, "pstart") == 0) PRESS_START = val;
  else if (strcmp(name, "pend")   == 0) PRESS_END   = val;
  else if (strcmp(name, "zlift")  == 0) Z_LIFT      = val;
  else if (strcmp(name, "ywiggle") == 0) Y_WIGGLE   = val;
  else if (strcmp(name, "ypeel1") == 0) Y_PEEL1     = val;
  else if (strcmp(name, "ypeel2") == 0) Y_PEEL2     = val;
  else if (strcmp(name, "ypeel3") == 0) Y_PEEL3     = val;
  else if (strcmp(name, "ypspeed") == 0) Y_PEEL_SPEED = constrain(val, 10, 200);
  else if (strcmp(name, "pwait")  == 0) PAGE_WAIT    = val;
  else return false;
  return true;
}

// ===== コマンド処理 =====
void checkSerialInput() {
  if (!Serial.available()) return;

  char cmd[32];
  readSerialLine(cmd, sizeof(cmd));
  for (int i = 0; cmd[i]; i++) cmd[i] = tolower((unsigned char)cmd[i]);

  // === rewind / rw（1ページ目に戻る。rewind.ino）===
  if (handleRewindCommand(cmd)) return;

  // === help ===
  if (strcmp(cmd, "help") == 0 || strcmp(cmd, "h") == 0 || strcmp(cmd, "?") == 0) {
    Serial.println(F("========== HELP =========="));
    Serial.println(F("--- 基本操作 ---"));
    Serial.println(F("  start / s        : 動作開始"));
    Serial.println(F("  stop / pause / p : 一時停止"));
    Serial.println(F("  resume / r       : 再開"));
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
    Serial.println(F("--- キャリブレーション ---"));
    Serial.println(F("  table            : キャリブテーブル表示"));
    Serial.println(F("  oz <slot> <val>  : Z角度を設定（例: oz 5 43）"));
    Serial.println(F("  calib_reset      : キャリブデータ消去"));
    Serial.println(F("--- テスト ---"));
    Serial.println(F("  t / tap          : タップ動作を1回"));
    Serial.println(F("  test <page>      : 指定ページのZ値で1ページ分動作"));
    Serial.println(F("--- 詳細設定 ---"));
    Serial.println(F("  set              : 設定一覧を表示"));
    Serial.println(F("  set <name> <val> : 設定変更"));
    Serial.println(F("                     yhome/zhome : 待機位置（めくり終えたあと）"));
    Serial.println(F("                     ybase/zbase : めくり開始位置（ここを経由してめくる）"));
    Serial.println(F("                     ymin/ymax/zmin/zmax"));
    Serial.println(F("                     pstart/pend : ページ押さえ角度"));
    Serial.println(F("                     zlift : タップ後に持ち上げるZ角度"));
    Serial.println(F("                     ywiggle : タップ中のY揺らし幅"));
    Serial.println(F("                     ypeel1/2/3 : めくるときのY角度"));
    Serial.println(F("                     ypspeed : めくりの速さ% (10~200, 標準100)"));
    Serial.println(F("                     pwait : めくり後の待ち 秒 (0~255, 標準2)"));
    Serial.println(F("                     zmin は 0 未満も可（最小 -14 程度）"));
    Serial.println(F("--- 1ページ目に戻る ---"));
    Serial.println(F("  rewind           : 戻す動作を実行してページを1に"));
    Serial.println(F("  rw               : 戻す動作の設定を表示"));
    Serial.println(F("  rw <段> <Y> <Z> <速さ> <待ちms> : 段を設定（段 0~7）"));
    Serial.println(F("  rw n <段数>      : 使う段数 0~8"));
    Serial.println(F("  rw go <段>       : その段の位置へ動かす（停止中）"));
    Serial.println(F("--- サーボ補正（サーボ交換時）---"));
    Serial.println(F("  scal             : 補正を表示"));
    Serial.println(F("  scal y a1 b1 a2 b2 : Y軸 a1->b1, a2->b2 で補正"));
    Serial.println(F("  scal z a1 b1 a2 b2 : Z軸 同上"));
    Serial.println(F("  scal off         : 補正なしに戻す"));
    Serial.println(F("--- 本の設定 ---"));
    Serial.println(F("  pages <num>      : 総ページ数変更 例: pages 320"));
    Serial.println(F("  pages            : 現在の総ページ数を表示"));
    Serial.println(F("--- その他 ---"));
    Serial.println(F("  help / h / ?     : このヘルプ"));
    Serial.println(F("=========================="));
    return;
  }

  // === start ===
  bool wantsRun = strcmp(cmd, "start") == 0 || strcmp(cmd, "s") == 0
               || strcmp(cmd, "r") == 0 || strcmp(cmd, "resume") == 0;
  if (wantsRun && currentPage >= totalPages) {
    Serial.println(F(">> 最後のページです。'rewind' で1ページ目に戻してください"));
    return;
  }
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
  if (strncmp(cmd, "z ", 2) == 0) {
    if (isPaused) {
      int req     = atoi(cmd + 2);
      int clamped = constrain(req, Z_MIN, Z_MAX);
      writeZRaw(clamped);
      Serial.print(F(">> Z -> "));
      Serial.print(clamped);
      if (clamped != req) Serial.print(F(" [LIMIT]"));
      Serial.println();
    } else {
      Serial.println(F(">> 一時停止中のみ使用可"));
    }
    return;
  }

  // === y <angle> ===
  if (strncmp(cmd, "y ", 2) == 0 && cmd[2] != '+' && cmd[2] != '-') {
    if (isPaused) {
      int req     = atoi(cmd + 2);
      int clamped = constrain(req, Y_MIN, Y_MAX);
      writeYRaw(clamped);
      Serial.print(F(">> Y -> "));
      Serial.print(clamped);
      if (clamped != req) Serial.print(F(" [LIMIT]"));
      Serial.println();
    } else {
      Serial.println(F(">> 一時停止中のみ使用可"));
    }
    return;
  }

  // === z+ / z- ===
  if (strcmp(cmd, "z+") == 0 || strcmp(cmd, "z-") == 0) {
    if (isPaused) {
      int next = constrain(zAngleNow + (cmd[1] == '+' ? 1 : -1), Z_MIN, Z_MAX);
      writeZRaw(next);
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
      int next = constrain(yAngleNow + (cmd[1] == '+' ? 1 : -1), Y_MIN, Y_MAX);
      writeYRaw(next);
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

  // === calib_reset ===
  if (strcmp(cmd, "calib_reset") == 0) {
    for (int i = 0; i < calibSections; i++) zOffsets[i] = Z_TOUCH_DEFAULT;
    EEPROM.write(EEPROM_MAGIC_ADDR, 0x00);
    Serial.println(F(">> CALIB RESET"));
    printOffsetTable();
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

  // === scal: サーボ補正 ===
  // scal                       : 表示
  // scal y <a1> <b1> <a2> <b2> : 設定上の a1 を実際は b1、a2 を b2 で出す（Y軸）
  // scal z <a1> <b1> <a2> <b2> : 同じくZ軸
  // scal off                   : 両軸とも補正なしに戻す（測り直すときはまずこれ）
  if (strcmp(cmd, "scal") == 0) {
    printServoCal();
    return;
  }
  if (strcmp(cmd, "scal off") == 0) {
    int idY[4] = {0, 0, 180, 180};
    for (int i = 0; i < 4; i++) { yCal[i] = idY[i]; zCal[i] = idY[i]; }
    saveServoCalToEEPROM();
    writeYRaw(yAngleNow);   // 今の位置を補正なしで出し直す
    writeZRaw(zAngleNow);
    Serial.println(F(">> SERVO CAL OFF"));
    printServoCal();
    return;
  }
  if (strncmp(cmd, "scal ", 5) == 0 && (cmd[5] == 'y' || cmd[5] == 'z') && cmd[6] == ' ') {
    int v[4];
    if (sscanf(cmd + 7, "%d %d %d %d", &v[0], &v[1], &v[2], &v[3]) != 4) {
      Serial.println(F(">> 書式: scal <y|z> <a1> <b1> <a2> <b2>  例: scal z 2 6 90 95"));
      return;
    }
    if (v[0] == v[2]) {
      Serial.println(F(">> 基準の2点は違う角度にしてください (a1 != a2)"));
      return;
    }
    int* c = (cmd[5] == 'y') ? yCal : zCal;
    for (int i = 0; i < 4; i++) c[i] = v[i];
    saveServoCalToEEPROM();
    writeYRaw(yAngleNow);   // 今の位置を新しい補正で出し直す
    writeZRaw(zAngleNow);
    Serial.println(F(">> SERVO CAL SET"));
    printServoCal();
    return;
  }

  // === set: 設定一覧を表示 ===
  if (strcmp(cmd, "set") == 0) {
    printSettings();
    return;
  }

  // === set <name> <val>: 設定変更 ===
  if (strncmp(cmd, "set ", 4) == 0) {
    char name[8];
    int  val = 0;
    if (sscanf(cmd + 4, "%7s %d", name, &val) != 2) {
      Serial.println(F(">> 書式: set <name> <val>  例: set yhome 90"));
      return;
    }
    // zmin だけは 0° 未満を許可する（Z軸はパルス幅制御でマイナスへ動かせる）
    bool allowNegative = (strcmp(name, "zmin") == 0);
    int  lo = allowNegative ? -30 : 0;
    if (val < lo || val > 255) {
      Serial.print(F(">> 範囲外です ("));
      Serial.print(lo);
      Serial.println(F("〜255)"));
      return;
    }

    // 変更前の値を控え、破綻したら戻す
    int oy = Y_HOME, oz = Z_HOME, oyl = Y_MIN, oyu = Y_MAX, ozl = Z_MIN, ozu = Z_MAX;
    int ops = PRESS_START, ope = PRESS_END;

    if (!applySetting(name, val)) {
      Serial.println(F(">> 不明な設定名"));
      Serial.println(F("   yhome/zhome/ybase/zbase/ymin/ymax/zmin/zmax/pstart/pend"));
      Serial.println(F("   zlift/ywiggle/ypeel1/ypeel2/ypeel3/ypspeed/pwait"));
      return;
    }

    if (Y_MIN >= Y_MAX || Z_MIN >= Z_MAX) {
      Y_HOME = oy;  Z_HOME = oz;
      Y_MIN  = oyl; Y_MAX  = oyu;
      Z_MIN  = ozl; Z_MAX  = ozu;
      PRESS_START = ops; PRESS_END = ope;
      Serial.println(F(">> 却下: MIN は MAX より小さくしてください"));
      return;
    }

    saveSettingsToEEPROM();
    Serial.print(F(">> SET "));
    Serial.print(name);
    Serial.print(F(" = "));
    Serial.println((strcmp(name, "ypspeed") == 0) ? Y_PEEL_SPEED : val);

    if (Y_HOME < Y_MIN || Y_HOME > Y_MAX || Z_HOME < Z_MIN || Z_HOME > Z_MAX) {
      Serial.println(F(">> 注意: HOME がリミット範囲外です"));
    }
    if (PRESS_START > Z_MAX || PRESS_END > Z_MAX) {
      Serial.println(F(">> 注意: 押さえ角度が zmax を超えています"));
    }
    printSettings();
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
  if (strncmp(cmd, "test ", 5) == 0) {
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
      yMotion();      // 末尾で Y と Z を同時にホームへ戻す
      pressMotion();  // めくったページが浮くので押さえる
      currentPage = savedPage;
    } else {
      Serial.println(F(">> ページ範囲外"));
    }
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
