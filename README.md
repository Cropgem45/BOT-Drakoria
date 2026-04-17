# Bot Drakoria - Fechamento de Producao

Bot administrativo em `Python + discord.py 2.x`, com operacao orientada por ID, persistencia em SQLite e paineis persistentes para uso real em producao.

## Sistemas Ativos

- `Registrar-se` (registro inicial automatico por painel)
- `Cadastro Oficial` (cadastro em etapas, validacao de idade, cargo de membro e nickname)
- `Programa Beta Tester` (candidatura, aprovacao/reprovacao, cargo e carteirinha)
- `Tickets` (painel, abertura, atribuicao, status, encerramento e transcricao)
- `Anuncios` (editor via modal, permissao por cargos e auditoria)
- `Bate-ponto por voz da staff` (sessao automatica, tolerancia, relatorios e dashboard de gestao)
- `Healthcheck` e `Server Map` administrativos

## Estrutura

```text
BOT Drakoria/
|-- .env.example
|-- bot.py
|-- requirements.txt
|-- README.md
|-- app/
|   |-- launcher.py
|   |-- cogs/
|   |-- core/
|   |-- repositories/
|   `-- services/
|-- config/
|   `-- example_config.json
|-- data/
`-- docs/
    |-- commands_reference.md
    |-- final_production_checklist.md
    |-- operational_checklist.md
    `-- system_overview.md
```

## Requisitos

- Python 3.12+ (recomendado)
- Permissoes do bot no Discord para cargos, canais, embeds, mensagens e anexos

## Instalacao

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Variaveis de Ambiente

Copie `.env.example` para `.env` e ajuste:

- `DISCORD_TOKEN`: token do bot
- `CONFIG_PATH`: caminho do JSON de configuracao
- `DATABASE_PATH`: caminho do SQLite
- `LOG_LEVEL`: `INFO`, `DEBUG`, `WARNING`, `ERROR`

## Executar

```powershell
python bot.py
```

## Comandos Principais

Consulte a referencia completa em `docs/commands_reference.md`.

- `/admin healthcheck`
- `/admin server_map`
- `/cadastro status`
- `/cadastro publicar_painel`
- `/beta_program publicar_painel`
- `/ticket painel`
- `/ticket abrir`
- `/ticket fechar`
- `/anuncio anuncio`
- `/pontos estado`
- `/pontos encerrar`
- `/pontos listar`
- `/pontos tolerancias`
- `/pontos diagnosticar`
- `/pontos limpar`
- `/pontos staff`
- `/pontos gestao`
- `/pontos resumo`

## Configuracao

O arquivo `config/example_config.json` e validado no boot. Se faltar campo obrigatorio ou existir ID invalido, a inicializacao falha com mensagem clara.

Blocos principais:

- `guild`
- `channels`
- `categories`
- `roles`
- `logs`
- `permissions`
- `voice_points`
- `tickets`
- `announcements`
- `registration_panel`
- `member_registration`
- `beta_program`
- `management_dashboard`

## Operacao e Homologacao

- Checklist final de producao: `docs/final_production_checklist.md`
- Visao tecnica dos modulos: `docs/system_overview.md`
- Checklist operacional rapido: `docs/operational_checklist.md`
- Deploy 24/7 sem PC ligado (Oracle Free): `docs/oracle_free_deploy.md`

## Troubleshooting Rapido

- Erro de boot: revisar `.env` e JSON de config
- Comando sem permissao: revisar `permissions` por ID
- Painel sem responder: republicar painel pelo comando administrativo correspondente
- Divergencia operacional: rodar `/admin healthcheck` e revisar logs
