// testrun.ino — 全ページ通しテスト

void saveTestrunState() {
  EEPROM.write(EEPROM_TESTRUN_ADDR,     EEPROM_TESTRUN_MAGIC);
  EEPROM.write(EEPROM_TESTRUN_ADDR + 1, (uint8_t)(testrunPage >> 8));
  EEPROM.write(EEPROM_TESTRUN_ADDR + 2, (uint8_t)(testrunPage & 0xFF));
}

void clearTestrunState() {
  EEPROM.write(EEPROM_TESTRUN_ADDR, 0x00);
}

void runTestrun() {
  checkSerialInput();
  if (!isTestrun) return;
  delay(1500);

  int savedPage = currentPage;
  currentPage   = testrunPage;

  Serial.print(F("[TESTRUN] p."));
  Serial.print(testrunPage);
  Serial.print(F(" / "));
  Serial.print(totalPages);
  Serial.print(F("  Z:"));
  Serial.print(getZTarget());
  Serial.println(F("deg"));

  logStatus("TEST");
  tapMotion();
  yMotion();
  moveSmooth(zaxis, getZHold(), Z_HOME);

  currentPage = savedPage;
  Serial.println(F("------ PAGE DONE ------"));

  testrunPage += 2;
  if (testrunPage >= totalPages) {
    testrunPage = 1;
    Serial.println(F("=== TESTRUN: all pages done, restarting ==="));
  }
  saveTestrunState();
}
