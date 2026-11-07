Remove-Item -Path 'HKCU:\Software\Classes\vodmd' -Recurse -Force -ErrorAction SilentlyContinue
Write-Host '등록 해제 완료'
