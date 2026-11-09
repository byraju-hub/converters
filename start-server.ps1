# Raju's Converters 서버를 (꺼져 있을 때만) 창 없이 시작합니다.
$port = if ($env:VOD_PORT) { [int]$env:VOD_PORT } else { 8765 }
$up = $false
try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1', $port); $c.Close(); $up = $true } catch {}
if (-not $up) {
    $env:PYTHONIOENCODING = 'utf-8'
    Start-Process -WindowStyle Hidden -WorkingDirectory $PSScriptRoot `
        -FilePath (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -ArgumentList 'web.py'
}
