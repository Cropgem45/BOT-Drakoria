# VPS Deploy Runbook

Data do snapshot: 2026-08-30

Este documento registra o estado atual da VPS e o fluxo seguro para o proximo deploy. A ideia e reduzir surpresa quando formos alterar o bot ou o site, sem apagar nada nem tentar "limpar" o servidor no escuro.

## Estado atual confirmado

- VPS Hostinger em `187.127.36.212`, host `srv1645774.hstgr.cloud`
- Usuario SSH: `root`
- Acesso SSH por chave funcionando com `C:\Users\Murillo\.ssh\drakoria_github_actions`
- Bot ativo em `/var/www/bot-deploy`
- Site ativo em `/var/www/site`
- `drakoria-bot.service` esta ativo no systemd
- `drakoria-site` esta online no PM2
- O workflow de GitHub Actions `validate-and-deploy.yml` ja esta no `main`
- Os secrets do repositório ja existem: `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`

## O que vimos no servidor

- `/var/www/site` esta em um estado limpo o suficiente para operacao normal.
- `/var/www/bot` continua como copia legada com mudancas locais pendentes.
- O codigo que sobe em producao passou a viver em `/var/www/bot-deploy`.
- O estado persistente do bot passou a viver em `/var/lib/drakoria-bot`.
- Isso evita que o deploy novo herde sujeira do antigo worktree.

## Regra de ouro

- Nao apagar nada automaticamente na VPS.
- Nao fazer `git reset --hard`.
- Nao fazer `git checkout --`.
- Nao rodar limpeza agressiva sem antes saber exatamente quais arquivos sao do usuario e quais sao gerados.
- O codigo em producao deve ser atualizado somente em `/var/www/bot-deploy`.
- O estado mutavel do bot deve ficar fora do repositório, em `/var/lib/drakoria-bot`.

## Fluxo seguro para mudar o projeto

1. Fazer a mudanca no repositorio local.
2. Testar o que for possivel localmente.
3. Commitar apenas o que precisa ir para o deploy.
4. Dar push para `main`.
5. Conferir o run do GitHub Actions.
6. Confirmar no servidor se o bot/site ficaram no commit novo.

## Estrutura limpa do bot

- Codigo: `/var/www/bot-deploy`
- Banco e dados runtime: `/var/lib/drakoria-bot/data`
- Logs: `/var/lib/drakoria-bot/logs`
- Arquivo `.env`: `/var/www/bot-deploy/.env`
- Serviço systemd: `drakoria-bot.service`
- O banco configurado em `DATABASE_PATH` determina onde `donaters.json`, backups e cache da logo são gravados.

## Fluxo seguro quando o deploy falhar

1. Verificar se a falha veio de segredo ausente, permissao SSH, conflito de merge ou dependencia.
2. Conferir `git status` na VPS antes de pensar em limpar qualquer coisa.
3. Se a VPS estiver com alteracoes locais, registrar quais arquivos sao importantes antes de qualquer acao.
4. Corrigir a causa raiz no repositorio ou no workflow, nao por "limpeza geral".

## O que fazer antes do proximo deploy manual

- Confirmar qual dos dois alvos vai mudar: bot, site ou ambos.
- Se for bot, revisar o estado de `/var/www/bot-deploy` antes de qualquer pull manual.
- Se for site, revisar o estado de `/var/www/site`, que hoje aparenta estar normal.
- Evitar mexer em arquivos de dados, backups e logs sem justificativa clara.

## Evidencia de saude atual

- O workflow atual concluiu com sucesso no GitHub Actions.
- O bot responde na VPS.
- O site responde no PM2.

## Proximo passo recomendado

Quando for hora de mexer de novo, escolher um alvo pequeno e bem definido para mudar primeiro. Isso mantem o ciclo previsivel e reduz o risco de bagunca na VPS.
