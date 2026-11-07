# Vod to MD

유튜브 링크나 내 PC의 영상·오디오 파일을 **타임스탬프가 붙은 Markdown 스크립트**로 바꿔 주는 도구입니다.
웹 화면과 명령줄 두 가지로 쓸 수 있고, 변환은 모두 내 PC에서 돌아갑니다(무료, API 키 불필요).

## 특징

- **유튜브**: 자막(수동 → 자동)이 있으면 바로 사용, 없으면 오디오를 받아 음성인식
- **로컬 파일**: [faster-whisper](https://github.com/SYSTRAN/faster-whisper)로 음성인식 (ffmpeg 설치 불필요)
- **여러 개 한꺼번에**: 링크·파일을 섞어서 일괄 변환, 한 건이 실패해도 나머지는 계속
- **웹 화면**: 링크 붙여넣기 / 파일 드래그 앤 드롭, 진행률, 미리보기, 복사, `.md`·ZIP 다운로드
- **Claude 요약(선택)**: 문서 맨 위에 요약·핵심 포인트, 본문 중간에 소제목 자동 삽입

## 설치

Python 3.10 이상이 필요합니다.

```bash
git clone https://github.com/byraju-hub/vod-to-md.git
cd vod-to-md
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt     # macOS/Linux: .venv/bin/pip
```

## 사용법

### 웹 화면

```bash
web.bat                       # Windows: 브라우저가 자동으로 열립니다
.venv\Scripts\python web.py   # 직접 실행 → http://127.0.0.1:8765
```

포트를 바꾸려면 환경변수 `VOD_PORT`를 지정하세요. 변환된 `.md` 파일은 프로젝트 폴더의 `output/`에 자동 저장되며, 화면의 **저장 폴더** 버튼으로 탐색기에서 바로 열 수 있습니다.

### 서버 시작·종료 버튼 (선택)

웹 화면 오른쪽 위의 **서버 끄기** 버튼으로 서버를 끌 수 있습니다. 꺼진 뒤에는 화면 위에 **서버 시작** 배너가 나타나고,
`launcher.html`(즐겨찾기에 추가해 두면 편해요)을 열어도 같은 버튼으로 서버를 켤 수 있습니다.

서버 시작 버튼이 동작하려면 `vodmd://` 주소를 한 번 등록해야 합니다(현재 사용자 전용, 관리자 권한 불필요).

```powershell
powershell -ExecutionPolicy Bypass -File register-protocol.ps1     # 등록
powershell -ExecutionPolicy Bypass -File unregister-protocol.ps1   # 해제
```

처음 누르면 브라우저가 "앱을 열까요?"라고 묻는데, "항상 허용"을 체크하세요.

### 명령줄

```bash
vod2md.bat "https://youtu.be/XXXX"                   # 유튜브
vod2md.bat "D:\videos\sermon.mp4"                    # 로컬 파일
vod2md.bat URL1 URL2 "D:\a.mp4" -d 결과폴더          # 여러 개
vod2md.bat --list 목록.txt -d 결과폴더               # 한 줄에 하나씩 적은 목록 (# 주석)
vod2md.bat URL --whisper                             # 자막 무시, 음성인식 강제
vod2md.bat FILE -m medium -l ko                      # 모델·언어 지정
vod2md.bat URL --summarize                           # Claude 요약 + 소제목
```

## Whisper 모델 고르기

| 모델 | 크기 | 속도 (CPU) | 정확도 | 추천 |
|---|---|---|---|---|
| tiny | ~75MB | 가장 빠름 | 낮음 | 연결 테스트 |
| base | ~140MB | 빠름 | 낮음~보통 | 영어 위주 대략 받아쓰기 |
| **small** (기본) | ~460MB | 영상 길이의 약 1배 | 보통 | 깨끗한 음성 |
| medium | ~1.5GB | 약 2~3배 | 좋음 | **한국어 설교·강의** |
| large-v3 | ~3GB | 4~6배 이상 | 최고 | 정확도가 최우선일 때 |

처음 쓰는 모델은 자동으로 내려받습니다. 위 수치는 대략적인 경험치입니다.

## Claude 요약 설정

환경변수 `ANTHROPIC_API_KEY`를 설정하거나, 프로젝트 폴더에 `.env` 파일을 만들어 한 줄 적어 주세요.

```
ANTHROPIC_API_KEY=sk-ant-...
```

`.env`는 `.gitignore`에 들어 있어 커밋되지 않습니다. 요약이 실패해도 스크립트 변환 결과는 그대로 저장됩니다.

## 출력 예시

```markdown
# 영상 제목

- 출처: https://www.youtube.com/watch?v=...
- 길이: 12:34
- 변환 방식: 유튜브 수동자막 (ko)

## 스크립트

[00:01](https://www.youtube.com/watch?v=...&t=1s) 안녕하세요, 오늘은 ...
```

유튜브 영상은 타임스탬프를 누르면 해당 시점으로 이동합니다.

## 참고

- GPU는 쓰지 않고 CPU(int8)로만 동작합니다.
- 유튜브 다운로드는 [yt-dlp](https://github.com/yt-dlp/yt-dlp)를 사용합니다. 저작권이 있는 영상은 이용 약관과 법률을 지켜 사용하세요.
