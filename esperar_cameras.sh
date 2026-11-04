#!/usr/bin/env bash
DIR="$(cd "$(dirname "$0")" && pwd)"
LIMITE="${1:-90}"
inicio=$(date +%s)
IPS=$(grep -E '^CAMERA[0-9]*_IP=' "$DIR/.env" 2>/dev/null | cut -d= -f2 | tr -d '\r"'"'"' ')
for ip in $IPS; do
  ok=0
  while :; do
    if timeout 2 bash -c "exec 3<>/dev/tcp/$ip/554" 2>/dev/null; then ok=1; break; fi
    if [ $(( $(date +%s) - inicio )) -ge "$LIMITE" ]; then break; fi
    sleep 2
  done
  if [ "$ok" = 1 ]; then echo "Câmera $ip respondendo."; else echo "AVISO: câmera $ip não respondeu em ${LIMITE}s."; fi
done
exit 0
