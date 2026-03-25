#include <Arduino.h>
#include <Servo.h>

// ============================================================
// Arduino UNO 서보 제어 스케치
// ------------------------------------------------------------
// 1) setup(): 서보/시리얼 초기화
// 2) loop():
//    - updateServoPositions()로 "한 스텝씩" 부드럽게 이동
//    - 시리얼 명령을 읽어 목표각(target)을 갱신
// ============================================================

// 손가락 4개를 가정한 4채널 서보
Servo servos[4];
const int servoPins[4] = {2, 3, 4, 5};

// 현재 각도 상태값
int currentAngles[4] = {90, 90, 90, 90};

// 목표 각도 상태값
int targetAngles[4] = {90, 90, 90, 90};

// 마지막 이동 시각(ms)
unsigned long lastMoveTime = 0;

// 한 스텝(1도) 이동 사이의 간격(ms)
const unsigned long STEP_DELAY_MS = 30;

// 포즈 정의
const int poseOpen[4] = {20, 30, 35, 40};
const int poseBend[4] = {160, 150, 145, 140};
const int poseNeutral[4] = {90, 90, 90, 90};

// 즉시 각도 적용
// - setup()에서 전원 인가 직후 중립 자세를 확정할 때 사용.
void applyAngles(const int target[4]) {
  for (int i = 0; i < 4; i++) {
    int safe = constrain(target[i], 0, 180);
    servos[i].write(safe);
    currentAngles[i] = safe;
    targetAngles[i] = safe;
  }
  lastMoveTime = 0;  // 이동 플래그 리셋
}

// 목표 각도만 설정하고 즉시 반환
// - 실제 이동은 loop()에서 updateServoPositions()가 담당한다.
void setTarget(const int target[4]) {
  for (int i = 0; i < 4; i++) {
    targetAngles[i] = constrain(target[i], 0, 180);
  }
  // 이동 스케줄 시작 시점을 갱신
  lastMoveTime = millis();
}

// 논-블로킹 이동
// loop에서 매번 호출되어 부드러운 움직임을 제공한다
void updateServoPositions() {
  // 현재 시각(ms)
  unsigned long now = millis();

  if (now - lastMoveTime < STEP_DELAY_MS) {
    return;
  }

  // 이번 호출에서 실제로 각도 변화가 있었는지 추적
  bool moving = false;

  for (int i = 0; i < 4; i++) {
    // 현재값이 목표보다 작으면 +1도
    if (currentAngles[i] < targetAngles[i]) {
      currentAngles[i]++;
      moving = true;
    // 현재값이 목표보다 크면 -1도
    } else if (currentAngles[i] > targetAngles[i]) {
      currentAngles[i]--;
      moving = true;
    }
    // 변경 여부와 상관없이 현재 상태를 서보에 반영
    servos[i].write(currentAngles[i]);
  }
  
  if (moving) {
    lastMoveTime = now;
  }
}

// POSE 명령 처리 - 즉시 목표를 설정하고 반환
// 입력 예: "BEND", "OPEN", "NEUTRAL"
void handlePose(const String &poseName) {
  if (poseName == "BEND") {
    setTarget(poseBend);
  } else if (poseName == "OPEN") {
    setTarget(poseOpen);
  } else if (poseName == "NEUTRAL") {
    setTarget(poseNeutral);
  }
}

void setup() {
  Serial.begin(115200);

  // 4개 서보를 각각 핀에 연결
  for (int i = 0; i < 4; i++) {
    servos[i].attach(servoPins[i]);
  }
  
  // 전원 인가 직후에는 중립 자세로 맞춤
  applyAngles(poseNeutral);
  delay(300);
}

void loop() {
  // 핵심 개선: loop 시작에서 updateServoPositions() 호출
  updateServoPositions();

  // 시리얼 데이터 읽기 (논-블로킹)
  if (Serial.available() <= 0) {
    return;
  }

  // 한 줄 명령 형식:
  // 1) POSE:BEND      -> 미리 정의한 포즈로 이동
  // 2) ANGLE:120      -> 4개 서보 모두 동일 각도로 이동
  // 3) 90             -> 기존 브리지 호환용(숫자만)
  String line = Serial.readStringUntil('\n');
  line.trim();

  // 빈 줄은 무시
  if (line.length() == 0) {
    return;
  }

  // POSE 명령 처리
  if (line.startsWith("POSE:")) {
    String poseName = line.substring(5);
    poseName.trim();
    handlePose(poseName);
    return;
  }

  // ANGLE 명령 처리
  if (line.startsWith("ANGLE:")) {
    String angleText = line.substring(6);
    int angle = constrain(angleText.toInt(), 0, 180);
    int sameAngle[4] = {angle, angle, angle, angle};
    setTarget(sameAngle);
    return;
  }

  // 이전 브리지와의 호환: 숫자만 오면 4개를 같은 각도로 이동
  // 참고: String.toInt()는 숫자로 시작하지 않으면 0을 반환한다.
  // 현재 코드는 0도도 유효 각도이므로, 실제 운영에서는 입력 포맷을
  // Python 브리지에서 보장(POSE:/ANGLE:)하는 방식을 권장한다.
  int angleFallback = line.toInt();
  if (angleFallback >= 0 && angleFallback <= 180) {
    int sameAngle[4] = {angleFallback, angleFallback, angleFallback, angleFallback};
    setTarget(sameAngle);
  }
}
