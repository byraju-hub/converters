# Raju's Converters

**소개 페이지: <https://byraju-hub.github.io/converters/>** · [설치 가이드](docs/INSTALL.md) · [릴리스](https://github.com/byraju-hub/converters/releases)

유튜브 링크나 내 PC의 영상·오디오 파일을 **타임스탬프가 붙은 Markdown 스크립트**로, PDF 문서를 **제목·목록·표 구조를 살린 Markdown**으로 바꿔 주는 도구입니다. 이미지를 PDF로 묶거나, PDF를 이미지로 저장하고, **사진의 형식을 바꾸거나 긴 변 기준으로 한꺼번에 줄이고(HEIC → JPG 포함)**, **한글(.hwp·.hwpx) 문서를 PDF·Markdown·이미지로** 바꾸는 기능도 있습니다.
웹 화면과 명령줄 두 가지로 쓸 수 있고, 변환은 모두 내 PC에서 돌아갑니다(무료, API 키 불필요).

## 특징

- **유튜브**: 자막(수동 → 자동)이 있으면 바로 사용, 없으면 오디오를 받아 음성인식
- **로컬 파일**: [faster-whisper](https://github.com/SYSTRAN/faster-whisper)로 음성인식 (ffmpeg 설치 불필요)
- **여러 개 한꺼번에**: 링크·파일을 섞어서 일괄 변환, 한 건이 실패해도 나머지는 계속
- **웹 화면**: 링크 붙여넣기 / 파일 드래그 앤 드롭, 진행률, 미리보기, 복사, `.md`·ZIP 다운로드
- **PDF → MD**: 웹 화면의 **PDF → MD** 탭에서 PDF를 끌어다 놓으면 제목·목록·표를 살려 변환 (쪽 구분 표시 선택 가능). 글자 없이 이미지뿐인 **스캔 PDF**는 한국어 글자 인식(OCR, RapidOCR)으로 읽음 — 글자 쪽과 스캔 쪽이 섞여 있어도 됨
- **이미지 → PDF**: 여러 이미지를 번호 순서대로 PDF 한 개로 묶음. 썸네일을 끌어서 순서를 바꾸고, 쪽 크기(이미지에 맞춤 / A4)를 고름
- **PDF → 이미지**: PDF의 쪽을 PNG/JPG로 저장(해상도·쪽 범위 선택). `output` 폴더에 PDF 이름의 폴더로 저장되고 ZIP으로도 받음
- **사진 변환**: HEIC·JPG·PNG·WEBP 등을 JPG·PNG·WEBP로 바꾸고, **긴 변 길이(px)를 지정해 여러 장을 한꺼번에 리사이즈**. 작은 사진은 키우지 않고, 사진 방향을 바르게 맞추며, 위치(GPS) 같은 사진 정보는 기본으로 지움
- **한글 변환**: `.hwp`·`.hwpx`를 PDF, Markdown, 이미지로. 한컴오피스가 있는 PC에서는 한글이 원본 모양 그대로 PDF를 만들고(이미지도 여기서 파생), 한컴오피스가 없어도 Markdown은 직접 읽어서 만듭니다(`.hwpx`는 제목·표까지, `.hwp`는 글자 위주).
- **Claude 요약(선택)**: 문서 맨 위에 요약·핵심 포인트, 본문 중간에 소제목 자동 삽입

## 설치

**Windows 10/11**에서는 세 단계면 됩니다. 단계별 설명과 문제 해결은 **[설치 가이드](docs/INSTALL.md)**에 있습니다.

1. **Python을 설치**합니다 (3.10 이상, 3.12~3.14 권장). <https://www.python.org/downloads/> 에서 받고, 설치 첫 화면의 **"Add python.exe to PATH"를 반드시 체크**하세요.
2. **프로그램을 받습니다.** 이 페이지의 초록색 **Code → Download ZIP**을 누르고 압축을 풉니다. (`git clone https://github.com/byraju-hub/converters.git`도 됩니다.)
3. 폴더 안의 **`setup.bat`을 더블클릭**합니다. 약 650MB를 설치하며 3~10분 걸립니다. 끝나면 바탕화면에 **Raju's Converters** 아이콘이 생깁니다.

| 하고 싶은 일 | 방법 |
|---|---|
| 실행 | 바탕화면의 **Raju's Converters** 더블클릭 (또는 폴더의 `web.bat`) |
| 업데이트 | 폴더의 **`update.bat`** 더블클릭 (유튜브 변환이 갑자기 안 되면 먼저 해 보세요) |
| 삭제 | 설치 가이드의 [삭제](docs/INSTALL.md#삭제) 참고 |

필요한 것: 디스크 여유 약 1.5GB, 인터넷(설치할 때와 모델을 처음 내려받을 때), Chrome 또는 Edge 권장.
`setup.bat`은 Windows 전용입니다. macOS·Linux는 [직접 설치](docs/INSTALL.md#고급-직접-설치-macoslinux-포함)로 할 수 있지만 아직 시험해 보지 못했습니다.

## 사용법

### 웹 화면

바탕화면 아이콘을 더블클릭하면 서버가 켜지고 브라우저가 열립니다. 직접 실행하려면:

```bash
web.bat                       # Windows: 브라우저가 자동으로 열립니다 (검은 창을 닫으면 종료)
.venv\Scripts\python web.py   # 직접 실행 → http://127.0.0.1:8765
```

포트를 바꾸려면 환경변수 `VOD_PORT`를 지정하세요 (`web.bat`은 그 포트로 브라우저를 엽니다). 변환된 파일은 기본으로 프로젝트 폴더의 `output/`에 자동 저장되며, 화면의 **저장 폴더** 버튼으로 탐색기에서 바로 열 수 있습니다.

**저장 위치는 바꿀 수 있습니다.** 변환 목록 오른쪽 아래의 **저장 폴더 바꾸기**를 누르면 폴더 선택 창이 열리고, **경로 직접 입력**으로 `D:\변환결과`처럼 적어도 됩니다(없는 폴더는 자동으로 만듭니다). 고른 폴더는 설치 폴더의 `settings.json`에 기억되어 다시 켜도 유지되며, **기본 폴더로** 버튼으로 되돌립니다. 바꾼 뒤에 하는 변환부터 새 폴더에 저장되고, 이미 만든 파일은 옛 폴더에 그대로 남습니다. 지정한 폴더를 쓸 수 없게 되면(USB를 뺀 경우 등) 기본 폴더로 돌아가고 화면에 이유를 알려 줍니다.

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

화면 위쪽의 탭으로 **영상 → MD**, **PDF → MD**, **이미지 → PDF**, **PDF → 이미지**, **한글 변환**, **사진 변환**을 오갈 수 있습니다. 변환 목록과 저장 폴더는 두 탭이 함께 씁니다. 주소 끝에 `#pdf`, `#img2pdf`, `#pdf2img`, `#hwp`, `#imgconv`를 붙이면(예: `http://127.0.0.1:8765/#img2pdf`) 해당 탭으로 바로 열립니다.

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

### 사진 변환 (형식 바꾸기 · 긴 변 기준 리사이즈)

```bash
imgconv.bat 사진1.heic 사진2.jpg --format jpg --long 1600 -d 결과폴더   # HEIC→JPG + 긴 변 1600px로 줄이기
imgconv.bat *.png --format webp --quality 80                          # 형식만 바꾸기
```

- **긴 변 기준:** 가로·세로 중 긴 쪽이 지정한 길이(px)가 되도록 비율을 지켜 줄입니다. 이보다 작은 사진은 키우지 않습니다. 화면에서는 800/1280/1600/2048 중에서 고르거나 직접 적을 수 있습니다(100~20000px).
- **형식:** JPG, PNG, WEBP, 또는 원래 형식 유지(HEIC·BMP·TIFF·GIF는 JPG로). 투명한 부분은 JPG에서 흰색이 됩니다.
- **사진 정보:** 촬영 위치(GPS)·기기 같은 EXIF 정보는 기본으로 지웁니다(끌 수 있음). 사진 방향은 바르게 돌려서 저장하고, 색 프로필은 유지합니다.
- 사진이 한 장이면 저장 폴더에 파일로, 여러 장이면 폴더로 저장되고 ZIP으로도 받을 수 있습니다. 읽을 수 없는 사진이 섞여 있으면 업로드할 때 알려 줍니다(이미지 → PDF 탭도 이제 HEIC를 받습니다).

### 한글(HWP·HWPX) 변환

```bash
hwpconv.bat 문서.hwpx --to pdf                 # PDF (한컴오피스 필요)
hwpconv.bat 문서.hwp  --to md                  # Markdown (한컴오피스가 없어도 됨)
hwpconv.bat 문서.hwpx --to img --format jpg --dpi 200 -d 결과폴더   # 이미지 (한컴오피스 필요)
```

| 결과물 | 한컴오피스 있음 | 한컴오피스 없음 |
|---|---|---|
| **PDF** | 한글이 보이지 않게 열어 원본 모양 그대로 저장 | 불가 |
| **이미지** | 위 PDF를 쪽마다 PNG/JPG로 | 불가 |
| **Markdown** `.hwpx` | 파일을 직접 읽어 제목·문단·목록·표를 살림 | 같음 |
| **Markdown** `.hwp` | 한글이 `.hwpx`로 저장한 뒤 위와 같이 읽음 | 글자만 직접 읽음(표·서식 제외) |

- 한컴오피스는 Windows용이며 이 프로그램은 내 PC의 한글을 자동으로 조작합니다(파일당 10초 안팎). 변환 중 한글 화면은 보이지 않습니다.
- 한글이 중간에 멈추면(암호·확인 창 등) 3분 뒤 알아서 중단하고, 이 프로그램이 띄운 한글만 종료합니다. 사용자가 직접 열어 둔 한글 문서는 건드리지 않습니다.
- 암호가 걸린 문서와 배포용(읽기 전용) 문서는 변환할 수 없습니다. `.hwpx`의 그림은 Markdown에 넣지 못합니다(PDF·이미지로 바꾸면 보입니다).

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
- 한글 문서 PDF 변환은 한컴오피스의 자동화 기능을 사용하며, 한컴오피스 자체는 이 프로젝트에 포함되어 있지 않습니다(사용자 PC의 정품을 사용).
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
| Flask, PyAV, NumPy, olefile, pillow-heif | BSD 계열 (pillow-heif에는 LGPL인 libheif가 포함됨) |
| yt-dlp | Unlicense |
| pywin32 | PSF |
| anthropic SDK, RapidOCR, OpenCV | Apache-2.0 |
| PyMuPDF, pymupdf4llm | AGPL-3.0 |
| Whisper 모델 / PP-OCRv5 모델 | MIT / Apache-2.0 (실행할 때 내려받음) |
| Pretendard 글꼴 | SIL OFL 1.1 (인터넷에서 불러옴) |

이 도구들은 저장소에 포함하지 않고 `pip install -r requirements.txt`로 설치합니다.
PyPI의 PyAV에는 GPL로 빌드된 FFmpeg가 들어 있으니, 이 프로그램을 `.exe` 등으로 묶어 배포할 때는 FFmpeg의 라이선스도 따로 확인하세요.
