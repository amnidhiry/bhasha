# Start the speech service at logon, hidden. Run once (as your user) with the same token.
param([Parameter(Mandatory = $true)][string]$Token)
$run = Join-Path $PSScriptRoot "run.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$run`" -Token $Token"
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "bhasha speech" -Action $action -Trigger $trigger -Force
Write-Host "Registered. It starts at your next logon; start it now with: Start-ScheduledTask 'bhasha speech'"
