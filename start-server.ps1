# Raju's Converters 서버를 (꺼져 있을 때만) 창 없이 시작합니다.
#   -Open : 서버가 준비되면 브라우저로 화면까지 열어 줍니다 (바탕화면 바로가기가 사용)
param([switch]$Open)

$port = if ($env:VOD_PORT) { [int]$env:VOD_PORT } else { 8765 }

function Test-Port {
    try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1', $port); $c.Close(); return $true } catch { return $false }
}

if (-not (Test-Port)) {
    $env:PYTHONIOENCODING = 'utf-8'
    Start-Process -WindowStyle Hidden -WorkingDirectory $PSScriptRoot `
        -FilePath (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -ArgumentList 'web.py'
}

if ($Open) {
    for ($i = 0; $i -lt 80 -and -not (Test-Port); $i++) { Start-Sleep -Milliseconds 500 }   # 최대 40초 기다림
    Start-Process "http://127.0.0.1:$port"
}
