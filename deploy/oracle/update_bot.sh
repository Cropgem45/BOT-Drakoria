#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Erro: execute como root (use sudo)." >&2
  exit 1
fi

BRANCH="${1:-main}"
BOT_USER="drakoria"
APP_DIR="/opt/drakoria-bot/app"

if [[ ! -d "${APP_DIR}/.git" ]]; then
  echo "Erro: repositorio nao encontrado em ${APP_DIR}" >&2
  exit 1
fi

runuser -u "${BOT_USER}" -- git -C "${APP_DIR}" fetch --all --prune
runuser -u "${BOT_USER}" -- git -C "${APP_DIR}" checkout "${BRANCH}"
runuser -u "${BOT_USER}" -- git -C "${APP_DIR}" pull --ff-only origin "${BRANCH}"

runuser -u "${BOT_USER}" -- "${APP_DIR}/.venv/bin/pip" install --upgrade pip
runuser -u "${BOT_USER}" -- "${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

systemctl restart drakoria-bot.service
systemctl --no-pager --full status drakoria-bot.service
