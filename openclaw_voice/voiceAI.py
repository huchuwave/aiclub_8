
import os
import time
import requests
import json
import re
import subprocess
from datetime import datetime
import speech_recognition as sr
from gtts import gTTS

# --- 시스템 설정 영역 ---
ANS_FILE = "smart_inter_ans.mp3"  # 답변이 저장될 임시 파일명
OPENCLAW_PATH = "/home/pi/.npm-global/bin/openclaw" # 오픈클로 CLI 실행 파일 절대 경로

# --- 전역 변수 설정 ---
play_process = None  # 현재 스피커로 재생 중인 프로세스를 관리 (중단시키기 위함)
is_speaking = False  # 로빈이 현재 말을 하고 있는지 여부를 저장

def get_korean_width(text):
    """
    박스 너비 계산
    """
    width = 0
    for char in text:
        if re.match(r'[가-힣]', char): width += 2 # 한글은 2칸
        else: width += 1 # 영문/숫자/공백은 1칸
    return width

def print_welcome_box():
    """시작 메시지"""
    msg = "안녕하세요 후추님! 당신의 든든한 AI 비서 '로빈'입니다. 무엇을 도와드릴까요?"
    text_width = get_korean_width(msg)
    # 터미널 폰트 비율에 맞춰 테두리 길이를 계산 (글자 너비의 약 절반 정도의 기호 사용)
    border = "═" * (text_width // 2 + 4) 
    
    print(f"\n╔{border}╗")
    print(f"║  {msg}  ║")
    print(f"╚{border}╝\n")

def clean_text_for_speech(text):
    """음성 합성(TTS) 엔진이 기호나 이모티콘을 읽다가 오류가 나지 않도록 텍스트 가공"""
    # 1. 마크다운 기호(**, #) 제거
    text = text.replace('*', '').replace('#', '').replace('\n', ' ')
    # 2. 이모티콘 및 특수문자 제거 (한글, 영어, 숫자, 기본 문장부호만 유지)
    text = re.sub(r'[^가-힣a-zA-Z0-9\s\.\?\!]', '', text)
    # 3. 연속된 공백을 하나로 합치고 정리
    return re.sub(r'\s+', ' ', text).strip()

def stop_speaking():
    """사용자가 호출어를 부르면 현재 나오고 있는 목소리를 즉시 중단"""
    global play_process, is_speaking
    if play_process and play_process.poll() is None:
        print("\n🛑 [인터럽트] 답변을 즉시 중단하고 새 명령을 듣습니다.")
        play_process.terminate() # 재생 프로세스(mpg123) 강제 종료
        play_process = None
    is_speaking = False

def speak_async(text, skip_print=False):
    """
    비동기 방식으로 음성 재생
    소리가 나오는 동안에도 프로그램이 멈추지 않고 계속 다음 코드를 실행
    """
    global play_process, is_speaking
    if not text: return
    
    stop_speaking() # 새로운 말을 하기 전, 혹시 나오고 있을 이전 소리를 정리
    
    if not skip_print:
        print(f"\n🤖 로빈: {text}")
    
    speech_text = clean_text_for_speech(text)
    try:
        # Google TTS를 사용하여 텍스트를 음성 파일로 변환
        tts = gTTS(speech_text, lang='ko')
        tts.save(ANS_FILE)
        
        is_speaking = True # 말하기 상태 돌입
        # Popen을 사용하여 백그라운드에서 mpg123 실행 (hw:2,0 스피커 지정)
        play_process = subprocess.Popen(["mpg123", "-a", "hw:2,0", "-q", ANS_FILE])
    except Exception as e:
        print(f"❌ 음성 출력 오류: {e}")

def get_ai_response(user_text):
    """오픈클로 메인 두뇌(LLM)에 시스템 시간 정보와 함께 질문을 전달"""
    now = datetime.now()
    # 인공지능이 현재 시각을 정확히 알 수 있도록 프롬프트에 힌트를 추가합니다.
    time_hint = f"(참고: 현재 한국 시각은 {now.strftime('%Y년 %m월 %d일 %H시 %M분 %A')}입니다.) "
    full_message = time_hint + user_text
    
    try:
        # --agent main: 현재 대화 세션에 연결
        # --json: 결과값을 구조화된 데이터로 받아 정확한 답변만 추출
        cmd = [OPENCLAW_PATH, "agent", "--agent", "main", "--message", full_message, "--local", "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=45)
        
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if 'payloads' in data and len(data['payloads']) > 0:
                # 인공지능의 답변 내에 'pepper'라는 이름이 있다면 '후추'로 바꿉니다.
                return data['payloads'][0].get('text', "").replace("pepper", "후추")
        return "죄송해요, 대답을 가져오지 못했습니다."
    except: return "연결 실패"

def run_loop():
    """음성 비서의 핵심 메인 루프"""
    global is_speaking
    print("🔄 로빈 엔진 최적화 및 시스템 시각 동기화 중...")
    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 0.6  # 말이 끝난 후 기다리는 시간 (초)
    recognizer.dynamic_energy_threshold = True # 주변 소음에 맞춰 마이크 감도 자동 조절
    
    try:
        with sr.Microphone() as source:
            # 1. 주변 소음 측정 및 환경 적응
            print("🎧 주변 소음 측정 중 (2초)...")
            recognizer.adjust_for_ambient_noise(source, duration=2)
            
            # 2. 정식 시작 인사 (텍스트와 음성 일치)
            welcome_msg = "안녕하세요 후추님! 당신의 든든한 AI 비서 '로빈'입니다. 무엇을 도와드릴까요?"
            print_welcome_box()
            speak_async(welcome_msg, skip_print=True)
            
            while True:
                # [에코 방지 로직] 로빈이 말하는 중이면 감도를 확 높여서 자기 목소리를 무시하게 함
                if is_speaking:
                    recognizer.energy_threshold = 4500 # 큰 소리(후추님의 외침)에만 반응
                    if play_process and play_process.poll() is not None:
                        is_speaking = False # 재생이 끝났으면 말하기 상태 해제
                else:
                    recognizer.energy_threshold = 800 # 평소에는 민감하게 경청
                
                print(f"👂 귀를 기울이고 있습니다...", end='\r')
                
                try:
                    # 3. 마이크로 소리 듣기 (최대 5초간 대화 유지)
                    audio = recognizer.listen(source, timeout=1, phrase_time_limit=5)
                    # 4. Google 클라우드 엔진으로 음성 인식
                    user_text = recognizer.recognize_google(audio, language='ko-KR')
                    
                    if not user_text or len(user_text) < 2: continue
                    print(f"\n🎤 인식됨: [{user_text}]")
                    
                    # 5. 호출어 '로빈'이 포함되어 있는지 확인
                    if "로빈" in user_text:
                        stop_speaking() # 호출어를 들으면 즉시 하던 말을 멈춤!
                        
                        clean_cmd = user_text.replace("로빈", "").strip()
                        if not clean_cmd:
                            speak_async("네, 후추님! 듣고 있습니다.")
                        else:
                            # 진짜 답변 생성 및 비동기 재생
                            ai_response = get_ai_response(clean_cmd)
                            speak_async(ai_response)
                            
                except sr.WaitTimeoutError: continue # 아무 소리 없으면 다시 루프로
                except sr.UnknownValueError: continue # 해석 불가 소음 무시
                except Exception as e: pass

    except Exception as e:
        print(f"❌ 하드웨어 초기화 실패: {e}")

if __name__ == "__main__":
    try:
        run_loop()
    except KeyboardInterrupt:
        stop_speaking()
        print("\n🏁 로빈 비서 서비스를 종료합니다.")
