# Deploy temporario sem PC ligado

Este projeto esta pronto para rodar em servicos de cloud como Railway, Render ou uma VM gratuita. Para o bot atual, a opcao temporaria mais simples e segura e Railway com volume persistente para o SQLite.

## Opcao recomendada: Railway

1. Suba este repositorio para o GitHub.
2. No Railway, crie um projeto usando `Deploy from GitHub repo`.
3. Selecione este repositorio.
4. Confirme que o start command ficou:

```bash
python bot.py
```

5. Em `Variables`, configure:

```env
DISCORD_TOKEN=seu_token_do_discord
CONFIG_PATH=config/example_config.json
DATABASE_PATH=data/drakoria.sqlite3
LOG_LEVEL=INFO
```

6. Crie um Volume no servico do bot e monte em:

```text
/app/data
```

O volume e importante porque o bot usa SQLite. Sem ele, dados de tickets, pontos, paineis e cadastros podem ser perdidos em rebuild/redeploy.

## Opcao alternativa: Render

Use um `Background Worker` com:

```bash
pip install -r requirements.txt
```

como build command, e:

```bash
python bot.py
```

como start command.

Configure as mesmas variaveis de ambiente. Para uso real, adicione disco persistente para a pasta `data` ou migre o banco para um servico externo.

## Depois que subir

1. Abra os logs do servico.
2. Confirme que nao aparece erro de `DISCORD_TOKEN` ou `CONFIG_PATH`.
3. Veja se o bot ficou online no Discord.
4. Rode `/admin healthcheck` no servidor.

## Observacoes de seguranca

- Nunca suba `.env` para o GitHub.
- Nunca coloque o token do Discord dentro do codigo.
- Se o token ja vazou em algum print, commit ou mensagem, regenere no Discord Developer Portal.
