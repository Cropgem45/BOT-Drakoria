# Mercado Drakoria

MVP de mercado para Discord usando Discord.js v14 com persistencia local em JSON.

## Configuracao

Copie `.env.example` para `.env` e preencha:

```env
DISCORD_TOKEN=
CLIENT_ID=
GUILD_ID=
MARKET_CHANNEL_ID=
NEGOTIATION_CATEGORY_ID=
```

## Executar

```powershell
npm install
npm start
```

O bot registra o comando `/mercado` na guild configurada quando fica online.

## Fluxo

- `/mercado` abre o painel ephemeral.
- `Criar Anuncio` pede categoria e abre modal.
- O anuncio e salvo em `marketplace/data/listings.json` e publicado no canal do mercado.
- `Tenho Interesse` cria uma conversa privada entre vendedor e cliente.
- `Encerrar Anuncio` funciona apenas para o dono.
- Anuncios ativos expiram automaticamente apos 48 horas.
