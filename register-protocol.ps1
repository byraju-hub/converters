# vodmd:// 주소를 Windows 에 등록합니다 (현재 사용자 전용, 관리자 권한 불필요).
# 웹 화면의 "서버 시작" 버튼이 이 주소로 start-server.ps1 을 실행합니다.
# 되돌리려면 unregister-protocol.ps1 을 실행하세요.
$script = Join-Path $PSScriptRoot 'start-server.ps1'
$key = 'HKCU:\Software\Classes\vodmd'
New-Item -Path "$key\shell\open\command" -Force | Out-Null
Set-ItemProperty -Path $key -Name '(default)' -Value 'URL:Vod to MD'
New-ItemProperty -Path $key -Name 'URL Protocol' -Value '' -Force | Out-Null
Set-ItemProperty -Path "$key\shell\open\command" -Name '(default)' `
    -Value "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
Write-Host '등록 완료: vodmd:// -> start-server.ps1'
