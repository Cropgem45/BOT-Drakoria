# Deploy 24/7 no Oracle Cloud Free (sem PC ligado)

Este guia prepara o bot para rodar continuamente em uma VM Linux gratuita (Always Free), sem depender do seu computador local.

## 1) Provisionar a VM

1. Crie uma VM Linux (Ubuntu) no Oracle Cloud Free Tier.
2. Garanta acesso SSH com chave.
3. Conecte por SSH.

## 2) Subir o projeto na VM

No seu terminal local:

```bash
ssh ubuntu@SEU_IP_DA_VM
```

Dentro da VM, rode:

```bash
sudo apt-get update -y
sudo apt-get install -y git
git clone https://github.com/SEU_USUARIO/SEU_REPO.git
cd SEU_REPO
sudo bash deploy/oracle/bootstrap_oracle_vm.sh https://github.com/SEU_USUARIO/SEU_REPO.git main
```

Se o repositório for privado, use URL SSH e configure chave no servidor.

## 3) Configurar `.env`

Edite:

```bash
sudo nano /opt/drakoria-bot/app/.env
```

Use:

```env
DISCORD_TOKEN=SEU_TOKEN_AQUI
CONFIG_PATH=/opt/drakoria-bot/app/config/production_config.json
DATABASE_PATH=/opt/drakoria-bot/app/data/drakoria.sqlite3
LOG_LEVEL=INFO
```

## 4) Configurar JSON de produção

Edite:

```bash
sudo nano /opt/drakoria-bot/app/config/production_config.json
```

Ajuste IDs de canais/cargos/guild reais do seu servidor Discord.

## 5) Instalar serviço 24/7

```bash
cd /opt/drakoria-bot/app
sudo bash deploy/oracle/install_systemd_service.sh
```

Com isso o bot:
- inicia automaticamente no boot;
- reinicia sozinho se cair;
- roda em segundo plano.

## 6) Comandos úteis

Status:

```bash
sudo systemctl status drakoria-bot
```

Logs em tempo real:

```bash
sudo journalctl -u drakoria-bot -f
```

Reiniciar:

```bash
sudo systemctl restart drakoria-bot
```

Parar/Iniciar:

```bash
sudo systemctl stop drakoria-bot
sudo systemctl start drakoria-bot
```

Atualizar código:

```bash
cd /opt/drakoria-bot/app
sudo bash deploy/oracle/update_bot.sh main
```

## 7) Checklist rápido de produção

1. `systemctl status` sem erro.
2. Bot aparece online no Discord.
3. `/admin healthcheck` retorna OK.
4. Logs sem exceções críticas após startup.
