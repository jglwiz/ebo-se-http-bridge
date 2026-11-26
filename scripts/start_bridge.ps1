param(
    [string]$Distro = "Ubuntu-22.04"
)

# Start the EBO SE x86 HTTP bridge in WSL2 in a hidden background process
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$WslRoot = (wsl -d $Distro -- wslpath -u $RepoRoot).Trim()
$CliPath = Join-Path $PSScriptRoot 'ebo_cli.py'

wsl -d $Distro -u root -- bash -c "pkill -f ebo_server_x86.py 2>/dev/null || true; pkill -f '/opt/ebo/mediamtx' 2>/dev/null || true; pkill -9 qemu-arm 2>/dev/null || true; mkdir -p /opt/ebo; cp -f '$WslRoot/x86-bridge/start_wsl_bridge.sh' /opt/ebo/start_wsl_bridge.sh && sed -i 's/\r$//' /opt/ebo/start_wsl_bridge.sh && chmod +x /opt/ebo/start_wsl_bridge.sh"

Start-Process -FilePath 'wsl.exe' -ArgumentList '-d', $Distro, '-u', 'root', '--', '/opt/ebo/start_wsl_bridge.sh', $WslRoot -WindowStyle Hidden

for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 1
    try {
        python $CliPath status 2>$null
        if ($LASTEXITCODE -eq 0) { exit 0 }
    } catch {}
}
Write-Error "Bridge did not respond within 15s."
exit 1
