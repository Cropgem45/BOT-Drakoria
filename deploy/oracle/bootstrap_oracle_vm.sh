#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Erro: execute como root (use sudo)." >&2
  exit 1
fi

REPO_URL="${1:-}"
BRANCH="${2:-main}"

if [[ -z "${REPO_URL}" ]]; then
  echo "Uso: sudo bash deploy/oracle/bootstrap_oracle_vm.sh <repo_url> [branch]" >&2
  echo "Exemplo: sudo bash deploy/oracle/bootstrap_oracle_vm.sh https://github.com/usuario/BOT-Drakoria.git main" >&2
  exit 1
fi

BOT_USER="drakoria"
BOT_GROUP="drakoria"
BOT_HOME="/opt/drakoria-bot"
APP_DIR="${BOT_HOME}/app"

echo "[1/7] Instalando pacotes base..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y git python3 python3-venv python3-pip ca-certificates

echo "[2/7] Preparando usuario de servico..."
if ! id -u "${BOT_USER}" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "${BOT_HOME}" --shell /bin/bash "${BOT_USER}"
fi
install -d -o "${BOT_USER}" -g "${BOT_GROUP}" "${BOT_HOME}"

echo "[3/7] Clonando/atualizando repositorio..."
if [[ -d "${APP_DIR}/.git" ]]; then
  runuser -u "${BOT_USER}" -- git -C "${APP_DIR}" fetch --all --prune
  runuser -u "${BOT_USER}" -- git -C "${APP_DIR}" checkout "${BRANCH}"
  runuser -u "${BOT_USER}" -- git -C "${APP_DIR}" pull --ff-only origin "${BRANCH}"
else
  rm -rf "${APP_DIR}"
  runuser -u "${BOT_USER}" -- git clone --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
fi

echo "[4/7] Criando ambiente Python e instalando dependencias..."
runuser -u "${BOT_USER}" -- python3 -m venv "${APP_DIR}/.venv"
runuser -u "${BOT_USER}" -- "${APP_DIR}/.venv/bin/pip" install --upgrade pip
runuser -u "${BOT_USER}" -- "${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

echo "[5/7] Criando pastas de runtime..."
install -d -o "${BOT_USER}" -g "${BOT_GROUP}" "${APP_DIR}/data" "${APP_DIR}/logs"

echo "[6/7] Inicializando arquivos de configuracao (se ausentes)..."
if [[ ! -f "${APP_DIR}/.env" ]]; then
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
  chown "${BOT_USER}:${BOT_GROUP}" "${APP_DIR}/.env"
  chmod 600 "${APP_DIR}/.env"
fi

if [[ ! -f "${APP_DIR}/config/production_config.json" ]]; then
  cp "${APP_DIR}/config/example_config.json" "${APP_DIR}/config/production_config.json"
  chown "${BOT_USER}:${BOT_GROUP}" "${APP_DIR}/config/production_config.json"
fi

echo "[7/7] Resumo final"
cat <<EOF
Bootstrap concluido.

Proximos passos:
1) Edite ${APP_DIR}/.env:
   - DISCORD_TOKEN=...
   - CONFIG_PATH=${APP_DIR}/config/production_config.json
   - DATABASE_PATH=${APP_DIR}/data/drakoria.sqlite3
   - LOG_LEVEL=INFO

2) Revise IDs em ${APP_DIR}/config/production_config.json.

3) Instale e habilite o servico:
   cd ${APP_DIR}
   sudo bash deploy/oracle/install_systemd_service.sh
EOF
