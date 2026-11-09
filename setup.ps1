# Raju's Converters 설치 도우미 (Windows)
# 더블클릭으로 쓰려면 setup.bat 을 실행하세요. 여러 번 실행해도 안전합니다(이미 된 것은 건너뜁니다).
param(
    [switch]$Yes,               # 질문 없이 기본값으로 진행
    [switch]$NoShortcut,        # 바탕화면 바로가기를 만들지 않음
    [string]$ShortcutDir,       # 바로가기를 만들 폴더 (기본: 바탕화면)
    [switch]$Register,          # '서버 시작' 버튼용 vodmd:// 등록까지 함 (물어보지 않음)
    [switch]$NoLaunch           # 끝난 뒤 바로 실행하지 않음
)

$ErrorActionPreference = 'Continue'     # pip 의 경고(stderr)가 오류로 처리되지 않게. 성공 여부는 종료 코드로 확인한다
$root = $PSScriptRoot
Set-Location $root
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

function Step($n, $text) { Write-Host ""; Write-Host "[$n/5] $text" -ForegroundColor Cyan }
function Done($text)     { Write-Host "      $text" -ForegroundColor Green }
function Note($text)     { Write-Host "      $text" -ForegroundColor DarkGray }
function Fail($what, $help) {
    Write-Host ""
    Write-Host "설치를 멈췄어요: $what" -ForegroundColor Red
    foreach ($h in $help) { Write-Host "  - $h" -ForegroundColor Yellow }
    Write-Host ""
    Write-Host "해결이 안 되면 docs\INSTALL.md 의 '문제가 생겼을 때'를 보세요." -ForegroundColor Yellow
    exit 1
}
function Ask($question, $default) {
    if ($Yes) { return $default }
    $hint = if ($default) { '[Y/n]' } else { '[y/N]' }
    $a = Read-Host "      $question $hint"
    if ([string]::IsNullOrWhiteSpace($a)) { return $default }
    return ($a -match '^(y|yes|예|네|ㅇ)')
}

Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host "  Raju's Converters 설치" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green
Write-Host "  설치 위치: $root"

# ---------------------------------------------------------------- 1. Python
Step 1 "Python 찾는 중"
function Find-Python {
    # 인자를 배열로 넘기면 PowerShell 이 "-3" 을 "- 3" 으로 바꿔 파이썬이 멈추므로, 명령을 그대로 적는다.
    # 파이썬이 알려 주는 실제 실행 파일 경로(sys.executable)를 이후에 쓴다.
    $code = "import sys; print(sys.executable); print('%d.%d.%d' % sys.version_info[:3])"
    $tries = @(
        { & py -3 -c $code 2>$null },
        { & python -c $code 2>$null },
        { & python3 -c $code 2>$null }
    )
    foreach ($t in $tries) {
        try {
            $lines = @(& $t)
            # 마이크로소프트 스토어로 연결되는 가짜 python.exe 는 종료 코드가 0 이 아니거나 출력이 없어서 여기서 걸러진다
            if ($LASTEXITCODE -eq 0 -and $lines.Count -ge 2) {
                $exe = "$($lines[0])".Trim(); $ver = "$($lines[1])".Trim()
                if ($ver -match '^\d+\.\d+\.\d+$' -and (Test-Path $exe)) {
                    return @{ Exe = $exe; Version = [version]$ver }
                }
            }
        } catch {}
    }
    return $null
}
$py = Find-Python
if (-not $py) {
    Fail "Python 을 찾지 못했어요" @(
        "https://www.python.org/downloads/ 에서 Python 3.12 이상을 받아 설치하세요.",
        "설치 첫 화면에서 'Add python.exe to PATH'를 꼭 체크하세요.",
        "설치가 끝나면 setup.bat 을 다시 실행하세요.")
}
if ($py.Version -lt [version]'3.10') {
    Fail "Python $($py.Version) 은 너무 오래됐어요 (3.10 이상 필요)" @(
        "https://www.python.org/downloads/ 에서 새 버전을 설치하고 setup.bat 을 다시 실행하세요.")
}
Done "Python $($py.Version) 사용"
if ($py.Version -ge [version]'3.15') { Note "주의: 이 버전은 아직 시험해 보지 못했어요. 설치가 실패하면 Python 3.12~3.14 를 써 보세요." }

# ---------------------------------------------------------------- 2. 가상환경
Step 2 "전용 작업 공간(.venv) 만드는 중"
$venvPy = Join-Path $root '.venv\Scripts\python.exe'
$healthy = $false
if (Test-Path $venvPy) {
    & $venvPy -c "import sys" 2>$null
    $healthy = ($LASTEXITCODE -eq 0)
    if (-not $healthy) {
        Note "이전에 만든 .venv 가 망가져 있어서 다시 만들어요."
        Remove-Item -Recurse -Force (Join-Path $root '.venv')
    }
}
if (-not $healthy) {
    & $py.Exe -m venv (Join-Path $root '.venv')
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPy)) {
        Fail "작업 공간(.venv)을 만들지 못했어요" @(
            "폴더에 쓰기 권한이 있는지 확인하세요. 'Program Files' 같은 보호된 곳이 아닌 내 문서·바탕화면 아래에 두는 것이 좋아요.",
            "백신 프로그램이 막고 있다면 잠시 끄고 다시 시도하세요.")
    }
    Done ".venv 를 만들었어요"
} else {
    Done "이미 있어서 그대로 써요"
}

# ---------------------------------------------------------------- 3. 패키지
Step 3 "필요한 프로그램 설치 중 (약 650MB, 인터넷 속도에 따라 3~10분)"
Note "창이 멈춘 것처럼 보여도 설치 중이니 닫지 말고 기다려 주세요."
& $venvPy -m pip install --disable-pip-version-check --upgrade pip 2>&1 | Out-Null
& $venvPy -m pip install --disable-pip-version-check -r (Join-Path $root 'requirements.txt')
if ($LASTEXITCODE -ne 0) {
    Fail "패키지 설치에 실패했어요" @(
        "인터넷 연결을 확인하고 setup.bat 을 다시 실행하세요. (이미 받은 것은 건너뛰어 더 빨라요)",
        "회사·학교 네트워크라면 프록시나 보안 프로그램이 막고 있을 수 있어요.",
        "위에 빨간 글씨로 나온 마지막 오류 줄을 검색하거나 docs\INSTALL.md 를 참고하세요.")
}
Done "설치 완료"

# ---------------------------------------------------------------- 4. 확인
Step 4 "제대로 설치됐는지 확인하는 중"
& $venvPy -c "import flask, yt_dlp, faster_whisper, pymupdf, pymupdf4llm, rapidocr, PIL, anthropic, av, olefile, win32com.client, pillow_heif" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Fail "설치는 끝났는데 일부 프로그램을 불러오지 못해요" @(
        "setup.bat 을 한 번 더 실행해 보세요.",
        "계속되면 .venv 폴더를 지우고 setup.bat 을 다시 실행하세요.")
}
Done "모든 기능이 준비됐어요"

# ---------------------------------------------------------------- 5. 바로가기
Step 5 "바로가기 만들기"
$lnk = $null
if (-not $NoShortcut) {
    $dir = if ($ShortcutDir) { $ShortcutDir } else { [Environment]::GetFolderPath('Desktop') }
    try {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        $lnk = Join-Path $dir "Raju's Converters.lnk"
        $sh = New-Object -ComObject WScript.Shell
        $s = $sh.CreateShortcut($lnk)
        $s.TargetPath = (Get-Command powershell.exe).Source
        $s.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$(Join-Path $root 'start-server.ps1')`" -Open"
        $s.WorkingDirectory = $root
        $icon = Join-Path $root 'assets\converters.ico'
        if (Test-Path $icon) { $s.IconLocation = $icon }
        $s.Description = "Raju's Converters 열기"
        $s.Save()
        Done "바로가기를 만들었어요: $lnk"
    } catch {
        Note "바로가기를 만들지 못했어요 (괜찮아요, web.bat 으로 실행할 수 있어요): $($_.Exception.Message)"
        $lnk = $null
    }
} else {
    Note "건너뜀"
}

if ($Register -or (Ask "화면의 '서버 시작' 버튼을 쓰려면 등록이 필요해요(현재 사용자만 적용). 등록할까요?" $false)) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'register-protocol.ps1')
}

Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host "  설치가 끝났어요!" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green
if ($lnk) { Write-Host "  실행 방법: 바탕화면의 `"Raju's Converters`" 를 더블클릭" }
Write-Host "  다른 방법: 이 폴더의 web.bat 더블클릭 (검은 창이 보이고, 그 창을 닫으면 종료돼요)"
Write-Host "  처음 영상을 변환하면 음성인식 모델을 내려받아요(small 약 460MB). 한 번만 받아요."
Write-Host "  자세한 안내: docs\INSTALL.md"

if (-not $NoLaunch -and (Ask "지금 바로 실행할까요?" $true)) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'start-server.ps1') -Open
}
