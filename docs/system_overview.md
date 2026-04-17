# System Overview

Visao tecnica dos modulos ativos no fechamento de projeto.

## Core

- `app/core/bot.py`: inicializacao, carga de cogs, sync de comandos, eventos de runtime.
- `app/core/settings.py`: schema e validacao de configuracao.
- `app/core/server_map.py`: resolucao de IDs e parametros operacionais.
- `app/core/permissions.py`: camada central de permissao por role IDs.
- `app/core/views.py`: views persistentes e modais.

## Services

- `registration.py`: fluxo Registrar-se.
- `member_registration.py`: cadastro oficial em etapas.
- `beta_program.py`: fluxo de candidatura beta, revisao e carteirinha.
- `tickets.py`: abertura/controle/encerramento de tickets.
- `points.py`: expediente por voz, tolerancia, relatorios e dashboard.
- `diagnostics.py`: healthcheck e auditorias operacionais.

## Cogs

- `administration.py`: `healthcheck` e `server_map`.
- `member_registration.py`: operacao administrativa do cadastro oficial.
- `beta_program.py`: operacao administrativa do programa beta.
- `tickets.py`: painel e comandos de ticket.
- `announcements.py`: editor de anuncios.
- `points.py`: comandos operacionais e gerenciais de staff.

## Banco (SQLite)

Repositorio: `app/repositories/database.py`

Principais dominios persistidos:
- tickets
- registro/cadastro
- candidaturas beta
- voice point sessions/segments
- estado de paineis persistentes
- alertas operacionais

## Princípios Operacionais

- Regra principal por ID (guild/channel/role)
- Permissao centralizada
- Logs administrativos para auditoria
- Fail-fast de configuracao no boot
- Views persistentes para resiliencia pos-restart
