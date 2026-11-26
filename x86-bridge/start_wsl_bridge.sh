#!/usr/bin/env bash
set -e
APP="${EBO_DIR:-/opt/ebo}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="${1:-${EBO_SRC_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}}"

mkdir -p "$APP/lib" "$APP/bionic" /system/etc

# Ensure TUTK master hostnames resolve for Android bionic libc
cat > /system/etc/hosts << 'EOF'
127.0.0.1 localhost
47.107.189.8 all-c-master-85arrwe488ffwtalxet9.iotcplatform.com
34.80.133.17 all-c-master-85arrwe488ffwtalxet9.iotcplatform.com
139.162.174.232 all-c-master-85arrwe488ffwtalxet9.iotcplatform.com
EOF

# Sync project runtime files (self-contained; does not depend on repo/)
cp -f "$SRC/x86-bridge/ebo.html" "$APP/"
cp -f "$SRC/x86-bridge/ebo_mqtt.py" "$APP/"
cp -f "$SRC/x86-bridge/mediamtx.template.yml" "$APP/"
cp -f "$SRC/x86-bridge/sleep.svg" "$APP/"
cp -f "$SRC/x86-bridge/ebo_server_x86.py" "$APP/"
cp -f "$SRC/x86-bridge/ebo_bridge_439" "$APP/ebo_bridge"

# Sync local proprietary vendor binaries and runtime env
cp -f "$SRC/local/vendor/lib/"*.so "$APP/lib/"
cp -f "$SRC/local/vendor/bionic/linker" "$APP/bionic/"
cp -f "$SRC/local/vendor/bionic/"*.so "$APP/bionic/"
cp -f "$SRC/local/vendor/ioctl9930.bin" "$APP/ioctl9930.bin"
cp -f "$SRC/config/bridge.env" "$APP/.env"
sed -i 's/\r$//' "$APP/.env"
chmod +x "$APP/ebo_bridge" "$APP/bionic/linker" "$APP/mediamtx"

set -a
source "$APP/.env"
set +a

export EBO_DIR="$APP"
export EBO_PORT="${EBO_PORT:-8000}"
export EBO_BIND="${EBO_BIND:-0.0.0.0}"
export EBO_USE_QEMU=1
export EBO_USE_UNSHARE=1

sed -e "s/__STREAM_USER__/${EBO_STREAM_USER}/g" -e "s/__STREAM_PASS__/${EBO_STREAM_PASS}/g" \
    "$APP/mediamtx.template.yml" > "$APP/mediamtx.yml"

cd "$APP"
exec python3 "$APP/ebo_server_x86.py"
