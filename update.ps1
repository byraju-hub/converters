# Raju's Converters 업데이트 도우미 (Windows)
# 더블클릭으로 쓰려면 update.bat 을 실행하세요.
# 내 결과 파일(output 폴더)과 설정(.env)은 건드리지 않아요.
param(
    [switch]$Yes,               # 질문 없이 진행
    [string]$ZipPath,           # 인터넷 대신 이미 받아 둔 ZIP 파일로 업데이트
    [string]$ZipUrl = 'https://github.com/byraju-hub/converters/archive/refs/heads/main.zip'
)

$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot
Set-Location $root
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

function Step($n, $text) { Write-Host ""; Write-Host "[$n/3] $text" -ForegroundColor Cyan }
function Done($text)     { Write-Host "      $text" -ForegroundColor Green }
function Note($text)     { Write-Host "      $text" -ForegroundColor DarkGray }
function Ask($question, $default) {
    if ($Yes) { return $default }
    $hint = if ($default) { '[Y/n]' } else { '[y/N]' }
    $a = Read-Host "      $question $hint"
    if ([string]::IsNullOrWhiteSpace($a)) { return $default }
    return ($a -match '^(y|yes|예|네|ㅇ)')
}

$venvPy = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    Write-Host "아직 설치되지 않았어요. 먼저 setup.bat 을 실행하세요." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "Raju's Converters 업데이트" -ForegroundColor Green

# ---------------------------------------------------------------- 1. 최신 프로그램 받기
Step 1 "최신 버전 받기"
$updated = $false
if (-not $ZipPath -and (Test-Path (Join-Path $root '.git')) -and (Get-Command git -ErrorAction SilentlyContinue)) {
    git pull --ff-only
    if ($LASTEXITCODE -eq 0) { Done "git 으로 최신 버전을 받았어요"; $updated = $true }
    else { Note "git 으로 받지 못했어요(내가 고친 파일이 있으면 그럴 수 있어요). ZIP 방식으로 이어서 해요." }
}
if (-not $updated) {
    if (-not $ZipPath) {
        Write-Host "      GitHub 의 최신 ZIP 을 받아 이 폴더에 덮어써요. 내 결과(output)와 설정(.env)은 그대로 둬요." -ForegroundColor Yellow
        if (-not (Ask "계속할까요?" $true)) { Write-Host "취소했어요."; exit 0 }
    }
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("converters-update-" + [guid]::NewGuid().ToString('N').Substring(0, 8))
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    try {
        $zip = $ZipPath
        if (-not $zip) {
            $zip = Join-Path $tmp 'latest.zip'
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri $ZipUrl -OutFile $zip -UseBasicParsing
        }
        Expand-Archive -Path $zip -DestinationPath (Join-Path $tmp 'x') -Force
        $src = Get-ChildItem (Join-Path $tmp 'x') -Directory | Select-Object -First 1
        if (-not $src -or -not (Test-Path (Join-Path $src.FullName 'web.py'))) { throw "ZIP 안에서 프로그램 파일을 찾지 못했어요" }
        # 내 것(.venv, output, .env, backups)은 빼고 덮어쓴다
        robocopy $src.FullName $root /E /NFL /NDL /NJH /NJS /NP /XD .venv output backups .git .taste-skill __pycache__ /XF .env settings.json | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "파일을 복사하지 못했어요 (robocopy 오류 $LASTEXITCODE)" }
        Done "최신 파일로 덮어썼어요"
    } catch {
        Write-Host "      업데이트를 받지 못했어요: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "      인터넷 연결을 확인하거나, GitHub 에서 ZIP 을 직접 받아 이 폴더에 덮어쓰세요." -ForegroundColor Yellow
        exit 1
    } finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
}

# ---------------------------------------------------------------- 2. 패키지
Step 2 "필요한 프로그램 갱신 (유튜브가 바뀌면 yt-dlp 를 새로 받아야 해요)"
& $venvPy -m pip install --disable-pip-version-check -r (Join-Path $root 'requirements.txt')
if ($LASTEXITCODE -ne 0) { Write-Host "      패키지 설치에 실패했어요. 인터넷 연결을 확인하고 다시 실행하세요." -ForegroundColor Red; exit 1 }
& $venvPy -m pip install --disable-pip-version-check --upgrade yt-dlp
if ($LASTEXITCODE -ne 0) { Note "yt-dlp 갱신에 실패했어요. 나중에 다시 시도해도 돼요." } else { Done "yt-dlp 최신" }

# ---------------------------------------------------------------- 3. 안내
Step 3 "마무리"
Write-Host "      프로그램이 켜져 있었다면, 화면의 '서버 끄기'를 누른 뒤 다시 실행해야 새 버전이 적용돼요." -ForegroundColor Yellow
Done "업데이트가 끝났어요"
