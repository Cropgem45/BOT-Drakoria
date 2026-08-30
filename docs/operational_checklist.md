# Checklist Operacional do Drakoria

Checklist rapido para rotina de operacao e pos-deploy.

## 0. Deploy e VPS

- Ler o [VPS Deploy Runbook](./vps_deploy_runbook.md) antes de qualquer push que altere bot, site ou infraestrutura.
- Confirmar qual alvo vai mudar: bot, site ou ambos.
- Evitar limpeza agressiva na VPS sem registrar o estado dos arquivos primeiro.
- Se o deploy envolver a VPS, conferir depois se `drakoria-bot.service` e `drakoria-site` continuam saudaveis.

## 1. Startup

- Confirmar `.env` valido.
- Executar `python bot.py` (com auto-restart padrao a cada mudanca nos arquivos monitorados).
- Verificar ausencia de erro de config no terminal.
- Rodar `/admin healthcheck`.

## 2. Paineis

- `/cadastro publicar_painel`
- `/beta_program publicar_painel`
- `/ticket painel`
- Validar botoes apos reinicio do bot.

## 3. Cadastro Oficial

- Iniciar cadastro por painel.
- Validar fluxo em etapas.
- Validar reprova automatica por idade < minimo.
- Validar aplicacao de cargo e nickname ao concluir.
- Validar log e registro no banco.

## 4. Programa Beta

- Enviar candidatura pelo painel.
- Validar recebimento no canal de candidaturas.
- Aprovar e reprovar em cenarios separados.
- Validar cargo, DM, carteirinha e logs.

## 5. Tickets

- Abrir ticket por painel e por comando.
- Validar categoria, permissao e staff roles.
- Testar assumir, transferir, status e encerrar.
- Validar transcricao e log.

## 6. Staff Voice Points

- Entrar/sair/trocar entre calls validas.
- Validar inicio automatico, tolerancia e encerramento.
- Validar relatorio final e dashboard de gestao.
- Validar `/pontos estado`, `/pontos listar`, `/pontos resumo`.

## 7. Anuncios

- Publicar por `/anuncio anuncio`.
- Validar permissao por cargo.
- Validar embed final e log administrativo.

## 8. Integridade

- Rodar `/admin server_map`.
- Confirmar IDs resolvendo para canais/cargos existentes.
- Confirmar logs sendo entregues sem falhas silenciosas.
