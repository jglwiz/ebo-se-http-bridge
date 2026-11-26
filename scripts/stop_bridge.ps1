param(
    [string]$Distro = "Ubuntu-22.04"
)

# Stop the EBO SE x86 HTTP bridge in WSL2 and release the robot session
wsl -d $Distro -u root -- bash -c "pkill -f ebo_server_x86.py 2>/dev/null || true; pkill -f '/opt/ebo/mediamtx' 2>/dev/null || true; pkill -9 qemu-arm 2>/dev/null || true; pkill -f 'ffmpeg.*rtsp://.*8554/ebo' 2>/dev/null || true"
Write-Output "EBO SE x86 bridge stopped."
