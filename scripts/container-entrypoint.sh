#!/bin/sh
set -eu

if [ -z "${STREAMDESK_LOCAL_IPS:-}" ]; then
    STREAMDESK_LOCAL_IPS=$(python - <<'PY'
import socket
addresses = {row[4][0] for row in socket.getaddrinfo(socket.gethostname(), None)}
print(','.join(sorted(addresses | {'127.0.0.1', '::1'})))
PY
)
    export STREAMDESK_LOCAL_IPS
fi

mkdir -p "${STREAMDESK_DATA}" "${STREAMDESK_NATIVE_ROOT}" "${STREAMDESK_BROWSER_ROOT}"
chown -R streamdesk:streamdesk "${STREAMDESK_DATA}" "${STREAMDESK_NATIVE_ROOT}" "${STREAMDESK_BROWSER_ROOT}"
if [ ! -f "${STREAMDESK_DEFAULT_CLIP}" ]; then
    gosu streamdesk ffmpeg -hide_banner -loglevel error -nostdin \
        -f lavfi -i color=c=0x111827:s=1920x1080:r=30 \
        -f lavfi -i anullsrc=r=48000:cl=stereo -t 10 \
        -c:v libx264 -preset veryfast -pix_fmt yuv420p -c:a aac "${STREAMDESK_DEFAULT_CLIP}"
fi
bootstrap_state=$(gosu streamdesk python scripts/container_bootstrap.py state)
if [ "$bootstrap_state" = "empty" ]; then
    if [ "${STREAMDESK_ADMIN_PASSWORD:-}" = "" ] || [ "${STREAMDESK_ADMIN_USER:-}" = "" ]; then
        echo "STREAMDESK_ADMIN_USER und STREAMDESK_ADMIN_PASSWORD werden beim ersten Containerstart benötigt." >&2
        exit 64
    fi
    credentials_json=$(python scripts/container_bootstrap.py credentials)
    printf '%s\n' "$credentials_json" | STREAMDESK_ENGINE=0 gosu streamdesk python bootstrap.py
    unset credentials_json
fi
unset STREAMDESK_ADMIN_PASSWORD
exec gosu streamdesk "$@"
