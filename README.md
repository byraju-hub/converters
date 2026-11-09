# Raju's Converters

유튜브 링크나 내 PC의 영상·오디오 파일을 **타임스탬프가 붙은 Markdown 스크립트**로, PDF 문서를 **제목·목록·표 구조를 살린 Markdown**으로 바꿔 주는 도구입니다. 이미지를 PDF로 묶거나, PDF를 이미지로 저장하는 기능도 있습니다.
웹 화면과 명령줄 두 가지로 쓸 수 있고, 변환은 모두 내 PC에서 돌아갑니다(무료, API 키 불필요).

## 특징

- **유튜브**: 자막(수동 → 자동)이 있으면 바로 사용, 없으면 오디오를 받아 음성인식
- **로컬 파일**: [faster-whisper](https://github.com/SYSTRAN/faster-whisper)로 음성인식 (ffmpeg 설치 불필요)
- **여러 개 한꺼번에**: 링크·파일을 섞어서 일괄 변환, 한 건이 실패해도 나머지는 계속
- **웹 화면**: 링크 붙여넣기 / 파일 드래그 앤 드롭, 진행률, 미리보기, 복사, `.md`·ZIP 다운로드
- **PDF → MD**: 웹 화면의 **PDF → MD** 탭에서 PDF를 끌어다 놓으면 제목·목록·표를 살려 변환 (쪽 구분 표시 선택 가능). 글자 없이 이미지뿐인 **스캔 PDF**는 한국어 글자 인식(OCR, RapidOCR)으로 읽음 — 글자 쪽과 스캔 쪽이 섞여 있어도 됨
- **이미지 → PDF**: 여러 이미지를 번호 순서대로 PDF 한 개로 묶음. 썸네일을 끌어서 순서를 바꾸고, 쪽 크기(이미지에 맞춤 / A4)를 고름
- **PDF → 이미지**: PDF의 쪽을 PNG/JPG로 저장(해상도·쪽 범위 선택). `output` 폴더에 PDF 이름의 폴더로 저장되고 ZIP으로도 받음
- **Claude 요약(선택)**: 문서 맨 위에 요약·핵심 포인트, 본문 중간에 소제목 자동 삽입

## 설치

Python 3.10 이상이 필요합니다.

```bash
git clone https://github.com/byraju-hub/converters.git
cd converters
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

### 웹 화면의 탭

화면 위쪽의 탭으로 **영상 → MD**, **PDF → MD**, **이미지 → PDF**, **PDF → 이미지**를 오갈 수 있습니다. 변환 목록과 저장 폴더는 두 탭이 함께 씁니다. 주소 끝에 `#pdf`, `#img2pdf`, `#pdf2img`를 붙이면(예: `http://127.0.0.1:8765/#img2pdf`) 해당 탭으로 바로 열립니다.

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

PDF는 이렇게 변환합니다.

```bash
pdf2md.bat 문서.pdf                                  # 현재 폴더에 문서.md 생성
pdf2md.bat a.pdf b.pdf -d 결과폴더 --no-page-marks    # 여러 개, 쪽 구분선 없이
pdf2md.bat scan.pdf --no-ocr                         # 스캔 쪽의 글자 인식을 끔
```

### 이미지 ↔ PDF

```bash
python pdftools.py img2pdf 1.jpg 2.png 3.webp -o 묶음.pdf --size a4      # 이미지 -> PDF (fit=이미지에 맞춤, a4)
python pdftools.py pdf2img 문서.pdf -d 결과폴더 --format jpg --dpi 200 --pages "1-3,5"
```

- JPEG는 원본 그대로 PDF에 넣어 화질 손실이 없습니다. 사진 방향(EXIF)은 반영하고, 투명 배경은 흰색으로 채웁니다.
  PNG·BMP·GIF·TIFF는 손실 없이(PNG) 넣고, WEBP는 JPEG로 변환해 넣습니다. HEIC는 아직 지원하지 않습니다.
- 아주 긴 이미지(웹 전체 캡처 등)는 PDF 한 쪽의 길이 한계(약 14,000pt)에 맞춰 줄어듭니다.
- PDF → 이미지의 해상도는 100/150/220/300dpi 중에서 고르며, 클수록 선명하지만 용량이 커집니다.

### 스캔 PDF(글자 인식, OCR)

글자 없이 이미지뿐인 쪽만 골라서 [RapidOCR](https://github.com/RapidAI/RapidOCR)의 PP-OCRv5 **한국어** 모델로 읽습니다.
처음 쓸 때 모델(약 13MB)을 자동으로 내려받고, 이후에는 인터넷 없이 PC에서 돌아갑니다(쪽당 몇 초).
알아 둘 점:

- 글자만 읽습니다. 스캔 쪽의 표·글머리 기호 같은 구조는 살리지 못하고, 큰 글씨 한 줄은 제목(`##`)으로 추정합니다.
- 오타나 빠진 띄어쓰기가 있을 수 있어요. 문서 맨 위에 그 사실이 적히니 중요한 내용은 원본과 대조하세요.
- 한글·영문·숫자 위주입니다. 한자가 많은 문서는 정확도가 떨어집니다.
- 화질이 좋을수록 정확합니다(권장 300dpi 이상, 기울어지지 않게 스캔).

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

## 라이선스

Copyright (C) 2026 byraju

이 프로젝트는 **GNU Affero 일반 공중 사용 허가서 3판 이후(AGPL-3.0-or-later)** 로 공개합니다. 전문은 [LICENSE](LICENSE)를 보세요.
PDF 변환에 쓰는 [PyMuPDF·pymupdf4llm](https://github.com/pymupdf/pymupdf4llm)이 AGPL-3.0이라 프로젝트 전체를 같은 라이선스로 맞췄습니다.

- 자유롭게 쓰고 고쳐서 다시 배포할 수 있습니다. 다만 배포하는 결과물도 AGPL로, 소스 코드와 함께 공개해야 합니다.
- 수정한 버전을 **네트워크로 다른 사람에게 서비스**하는 경우에도 그 사용자에게 소스 코드를 제공해야 합니다(AGPL 13조). 화면 오른쪽 위 GitHub 링크가 소스 위치입니다.
- 개인 PC에서 혼자 쓰는 것은 아무 제약이 없습니다.

### 함께 쓰는 도구의 라이선스

| 도구 | 라이선스 |
|---|---|
| faster-whisper, CTranslate2, onnxruntime | MIT |
| Flask, PyAV, NumPy | BSD 계열 |
| yt-dlp | Unlicense |
| anthropic SDK, RapidOCR, OpenCV | Apache-2.0 |
| PyMuPDF, pymupdf4llm | AGPL-3.0 |
| Whisper 모델 / PP-OCRv5 모델 | MIT / Apache-2.0 (실행할 때 내려받음) |
| Pretendard 글꼴 | SIL OFL 1.1 (인터넷에서 불러옴) |

이 도구들은 저장소에 포함하지 않고 `pip install -r requirements.txt`로 설치합니다.
PyPI의 PyAV에는 GPL로 빌드된 FFmpeg가 들어 있으니, 이 프로그램을 `.exe` 등으로 묶어 배포할 때는 FFmpeg의 라이선스도 따로 확인하세요.
