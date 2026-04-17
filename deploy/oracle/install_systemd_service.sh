#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Erro: execute como root (use sudo)." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_SOURCE="${SCRIPT_DIR}/drakoria-bot.service"
SERVICE_TARGET="/etc/systemd/system/drakoria-bot.service"

if [[ ! -f "${SERVICE_SOURCE}" ]]; then
  echo "Erro: arquivo de service nao encontrado em ${SERVICE_SOURCE}" >&2
  exit 1
fi

install -m 0644 "${SERVICE_SOURCE}" "${SERVICE_TARGET}"
systemctl daemon-reload
systemctl enable --now drakoria-bot.service

echo "Servico instalado e iniciado."
systemctl --no-pager --full status drakoria-bot.service
