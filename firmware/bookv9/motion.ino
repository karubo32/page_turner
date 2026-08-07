// motion.ino — サーボ動作関数

// ===== スムーズ移動 =====
// デフォルト引数は bookv9.ino の前方宣言側に記述（C++の仕様上、両方には書けない）
void moveSmooth(Servo& servo, int startPos, int endPos, float speedScale) {
  bool isY = (&servo == &yaxis);
  int minA = isY ? Y_MIN : Z_MIN;
  int maxA = isY ? Y_MAX : Z_MAX;
  startPos = constrain(startPos, minA, maxA);
  endPos   = constrain(endPos,   minA, maxA);
  int distance = abs(endPos - startPos);
  if (distance == 0) return;
  int step = (startPos < endPos) ? 1 : -1;
  for (int i = 0; i <= distance; i++) {
    int pos = startPos + step * i;
    float t = (float)i / distance;
    int d = (int)((10 + 40 * (1.0 - sin(t * PI))) * speedScale / globalSpeed);
    d = max(d, 1);
    // Z軸は 0° 未満も扱うためパルス幅で指令する
    if (isY) servo.write(pos);
    else     writeZRaw(pos);
    delay(d);
  }
}

// ===== 2軸同時スムーズ移動 =====
// 移動量の大きい方をステップ数の基準にし、もう一方は比率で追従させる。
// これで両軸が同時に動き出し、同時に到着する。
// デフォルト引数は bookv9.ino の前方宣言側に記述
void moveSmoothDual(int yStart, int yEnd, int zStart, int zEnd, float speedScale) {
  yStart = constrain(yStart, Y_MIN, Y_MAX);
  yEnd   = constrain(yEnd,   Y_MIN, Y_MAX);
  zStart = constrain(zStart, Z_MIN, Z_MAX);
  zEnd   = constrain(zEnd,   Z_MIN, Z_MAX);

  // max()/abs() はマクロで引数を複数回評価するため、先に変数へ入れておく
  int yDist = abs(yEnd - yStart);
  int zDist = abs(zEnd - zStart);
  int steps = (yDist > zDist) ? yDist : zDist;
  if (steps == 0) return;

  for (int i = 0; i <= steps; i++) {
    float t = (float)i / steps;
    yaxis.write(yStart + (int)round((yEnd - yStart) * t));
    writeZRaw(zStart + (int)round((zEnd - zStart) * t));
    int d = (int)((10 + 40 * (1.0 - sin(t * PI))) * speedScale / globalSpeed);
    d = max(d, 1);
    delay(d);
  }
}

// ===== ホームポジション復帰 =====
void goHome() {
  Serial.println(F(">> GO HOME"));
  moveSmooth(yaxis, yaxis.read(), Y_HOME, 2.0);
  moveSmooth(zaxis, zAngleNow, Z_HOME, 3.0);
  Serial.println(F(">> HOME POSITION"));
}

// ===== タップ動作 =====
void tapMotion() {
  int touchPos   = getZTarget();
  int liftOffset = 8;
  int zHold      = 160;
  int lift       = min(touchPos + liftOffset, zHold - 5);

  moveSmooth(zaxis, Z_HOME,      touchPos,    2.0);
  delay(80);
  moveSmooth(zaxis, touchPos,    lift,        2.0);
  moveSmooth(zaxis, lift,        lift - 2,    0.8);
  moveSmooth(zaxis, lift - 2,    lift + 15,   4.70);
  moveSmooth(yaxis, 90,        82,    8);
  moveSmooth(yaxis, 82,        90,    8);
  moveSmooth(zaxis, lift + 15,   lift + 11,   4.8);
  delay(500);
  moveSmooth(zaxis, lift +11,    lift + 15,   4.70);
  delay(150);
  moveSmooth(zaxis, lift + 15,   lift + 11,   4.8);
  moveSmooth(zaxis, lift + 11,   zHold,       2.0);
}

// ===== Y剥がし =====
// 最後のホーム復帰は Y と Z を同時に動かす（Z は現在位置から Z_HOME へ）
void yMotion() {
  moveSmooth(yaxis, Y_HOME, 80, 7.0);
  delay(500);
  moveSmooth(yaxis, 80, 65, 6.0);
  moveSmooth(yaxis, 65, 50, 3.0);
  moveSmoothDual(50, Y_HOME, zAngleNow, Z_HOME, 1.4);
}

// ===== ページ押さえ =====
// めくったページが浮くので、Z軸をさらに倒して押さえつけてから戻る。
// 角度はページ位置に応じて PRESS_START → PRESS_END で変化する。
void pressMotion() {
  int target = getPressAngle();

  if (target > Z_MAX) {
    Serial.print(F(">> 押さえ角度が Z_MAX で制限されました: "));
    Serial.print(target);
    Serial.print(F(" -> "));
    Serial.print(Z_MAX);
    Serial.println(F("  ('set zmax <val>' で上限を上げてください)"));
  }

  moveSmooth(zaxis, zAngleNow, target, 2.0);
  delay(PRESS_HOLD_MS);
  moveSmooth(zaxis, zAngleNow, Z_HOME, 2.0);
}
