# Divulgação automática de criadores

O bot monitora os criadores configurados em `creator_announcements` e publica no canal definido em `channel_id`.

## Regras atuais

- Twitch: divulga uma live ativa quando o título contém `Drakoria`, sem diferenciar maiúsculas e minúsculas.
- YouTube: divulga vídeos recentes quando o título ou a descrição contém `Drakoria`, sem diferenciar maiúsculas e minúsculas.
- Cada live/vídeo é publicado uma única vez; o histórico não é apagado quando a live termina.
- As mensagens usam `@everyone` quando `mention_everyone` está ativado.
- O Diogo está marcado como embaixador e recebe destaque dourado no embed.

## Credenciais privadas

Configure no `.env` da VPS, sem commitar:

```env
TWITCH_CLIENT_ID=...
TWITCH_CLIENT_SECRET=...
YOUTUBE_API_KEY=...
```

As credenciais da Twitch são obtidas no Twitch Developer Console. A chave do YouTube deve ter a YouTube Data API v3 habilitada no Google Cloud.

## Configuração de criadores

Edite a seção `creator_announcements` do arquivo de configuração privado usado pela VPS. O arquivo de exemplo contém os criadores iniciais e serve como referência, sem credenciais.

O intervalo padrão é de 60 segundos, com limite mínimo de 30 segundos. O sistema usa a playlist de uploads do YouTube para acompanhar apenas os vídeos recentes e preservar quota da API.

## Validação

Depois de configurar as credenciais e publicar uma alteração:

```bash
systemctl is-active drakoria-bot.service
journalctl -u drakoria-bot.service -n 100 --no-pager
```

Procure nos logs por `Conteúdo divulgado` e confirme a mensagem no canal `1508132406199324692`.
