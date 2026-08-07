// motion.ino — サーボ動作関数

// ===== スムーズ移動 =====
// デフォルト引数は bookv9.ino の前方宣言側に記述（C++の仕様上、両方には書けない）
void moveSmooth(Servo& servo, int startPos, int endPos, float speedScale) {
  int minA = (&servo == &yaxis) ? Y_MIN : Z_MIN;
  int maxA = (&servo == &yaxis) ? Y_MAX : Z_MAX;
  startPos = constrain(applyDirection(startPos), minA, maxA);
  endPos   = constrain(applyDirection(endPos),   minA, maxA);
  int distance = abs(endPos - startPos);
  if (distance == 0) return;
  int step = (startPos < endPos) ? 1 : -1;
  for (int i = 0; i <= distance; i++) {
    int pos = startPos + step * i;
    float t = (float)i / distance;
    int d = (int)((10 + 40 * (1.0 - sin(t * PI))) * speedScale / globalSpeed);
    d = max(d, 1);
    servo.write(pos);
    delay(d);
  }
}

// ===== ホームポジション復帰 =====
void goHome() {
  Serial.println(F(">> GO HOME"));
  moveSmooth(yaxis, yaxis.read(), Y_HOME, 2.0);
  moveSmooth(zaxis, zaxis.read(), Z_HOME, 3.0);
  Serial.println(F(">> HOME POSITION"));
}

// ===== タップ動作 =====
void tapMotion() {
  int touchPos  = getZTarget();
  int liftOffset = 8;
  int zHold     = getZHold();
  int lift      = min(touchPos + liftOffset, zHold - 5);

  moveSmooth(zaxis, Z_HOME,      touchPos,    2.0);
  delay(80);
  moveSmooth(zaxis, touchPos,    lift,        2.0);
  moveSmooth(zaxis, lift,        lift - 2,    0.8);
  moveSmooth(zaxis, lift - 2,    lift + 15,   4.70);
  moveSmooth(zaxis, lift + 15,   lift + 11,   4.8);
  delay(150);
  moveSmooth(zaxis, lift + 11,   zHold,       2.0);
}

// ===== Y剥がし =====
void yMotion() {
  moveSmooth(yaxis, Y_HOME, 80, 7.0);
  delay(500);
  moveSmooth(yaxis, 80, 65, 6.0);
  moveSmooth(yaxis, 65, 50, 3.0);
  moveSmooth(yaxis, 50, Y_HOME, 1.4);
}

// ===== ワイパー動作 =====
void wiperMotion() {
  Serial.println(F(">> WIPER START"));

  moveSmooth(yaxis, Y_HOME, wy5, 2.0);
  moveSmooth(zaxis, Z_HOME, wz2, 2.0);
  delay(2000);

  for (int i = 0; i < 5; i++) {
    moveSmooth(yaxis, wy1, wy2, 2.0);
    moveSmooth(zaxis, wz1, wz2, 2.0);
    moveSmooth(yaxis, wy2, wy1, 2.0);
    moveSmooth(zaxis, wz2, wz1, 2.0);
  }
  moveSmooth(yaxis, wy1, wy3, 2.0);

  for (int i = 0; i < 5; i++) {
    moveSmooth(yaxis, wy3, wy4, 2.0);
    moveSmooth(zaxis, wz1, wz2, 2.0);
    moveSmooth(yaxis, wy4, wy3, 2.0);
    moveSmooth(zaxis, wz2, wz1, 2.0);
  }

  moveSmooth(zaxis, wz1, Z_HOME, 2.0);
  moveSmooth(yaxis, wy3, Y_HOME, 2.0);

  Serial.println(F(">> WIPER DONE"));
}
