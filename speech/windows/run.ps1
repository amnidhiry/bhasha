# Start the speech service on port 8790. Set the same token as BHASHA_SPEECH_TOKEN in bhasha's .env.
param([string]$Token = $env:SPEECH_TOKEN, [string]$Engine = "kokoro", [string]$Device = "auto")
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not $Token) { throw "Pass -Token or set SPEECH_TOKEN: the service is reachable from the LAN." }
$env:SPEECH_TOKEN = $Token; $env:SPEECH_ENGINE = $Engine; $env:SPEECH_DEVICE = $Device
.\.venv\Scripts\python -m uvicorn bhasha_speech.app:app --host 0.0.0.0 --port 8790
