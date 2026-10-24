#!/bin/sh
# Run a temporary, metadata-only capture of the printer's network traffic.

SCRIPT_DIR=/mnt/UDISK/helper-script
TRACE_SCRIPT=$SCRIPT_DIR/scripts/cloud_trace.py
LOG_DIR=$SCRIPT_DIR/logs
LOG_FILE=$LOG_DIR/cloud-trace.log
DURATION=${1:-300}

if [ "$(id -u)" != 0 ]; then
    echo "[ERROR] Run this diagnostic as root." >&2
    exit 1
fi
if ! grep -q '^OPENWRT_BOARD=.*CR0CUF039C13' /etc/os-release 2>/dev/null; then
    echo "[ERROR] This diagnostic targets K3 board CR0CUF039C13." >&2
    exit 1
fi
case "$DURATION" in
    ''|*[!0-9]*) echo "Usage: $0 [duration-seconds] (15-1800)" >&2; exit 2 ;;
esac
if [ "$DURATION" -lt 15 ] || [ "$DURATION" -gt 1800 ]; then
    echo "Usage: $0 [duration-seconds] (15-1800)" >&2
    exit 2
fi
[ -f "$TRACE_SCRIPT" ] || { echo "[ERROR] Missing $TRACE_SCRIPT" >&2; exit 1; }
mkdir -p "$LOG_DIR" || exit 1
echo "[INFO] Capturing DNS, TCP endpoints, and visible TLS hostnames for ${DURATION}s."
echo "[INFO] The previous trace log will be replaced; no packet payload is saved."
python3 "$TRACE_SCRIPT" "$DURATION" "$LOG_FILE"
result=$?
echo "[INFO] Trace log: $LOG_FILE"
echo "[INFO] Review it with: cat $LOG_FILE"
exit "$result"
