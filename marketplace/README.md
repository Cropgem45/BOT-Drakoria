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
- `Tenho Interesse` (ou `Tenho o Item`) cria uma conversa privada entre as partes.
- `Encerrar Anuncio` funciona apenas para o dono.
- Anuncios ativos expiram automaticamente apos 48 horas.

---

# Detalhes Tecnicos

Este documento descreve como o Mercado Drakoria funciona internamente (arquitetura, eventos, persistencia e regras).

## Objetivo do Design

- UX rapida: poucos cliques e feedback imediato.
- Sem banco externo: persistencia local em JSON para facilitar deploy e manutencao.
- Interacoes 100% via Discord: botao, select menu e modal.
- Conversa privada: negociacao ocorre em canal privado temporario.

## Estrutura (Visao Geral)

Entrypoint e handlers:
- `marketplace/src/index.js`: inicializa o client e carrega comandos/eventos.
- `marketplace/src/handlers/commandHandler.js`: carrega slash commands de `src/commands/`.
- `marketplace/src/handlers/eventHandler.js`: registra os eventos de `src/events/`.

Eventos:
- `marketplace/src/events/ready.js`: sincroniza slash commands e publica/atualiza o painel fixo no canal do mercado.
- `marketplace/src/events/interactionCreate.js`: roteia clicks, select menus e modals.
- `marketplace/src/events/messageCreate.js`: captura prints colados (Ctrl+V) para anexar imagem ao anuncio.

Servicos:
- `marketplace/src/services/listingService.js`: cria anuncios, encerra, interesse e negociacao.
- `marketplace/src/services/panelService.js`: publica/atualiza o painel fixo e guarda `panel.json`.
- `marketplace/src/services/imageUploadService.js`: fluxo de adicionar imagem via print.
- `marketplace/src/services/listingStore.js`: persistencia de anuncios em `listings.json`.
- `marketplace/src/services/conversationStore.js`: persistencia de conversas em `conversations.json`.

Embeds e componentes:
- `marketplace/src/utils/embeds.js`: layout premium dos anuncios/painel/conversas.
- `marketplace/src/utils/componentIds.js`: padrao de `customId` usado nos componentes.

## Persistencia (Sem Banco)

Arquivos (criados automaticamente):
- `marketplace/data/listings.json`: anuncios.
- `marketplace/data/conversations.json`: conversas privadas abertas/encerradas.
- `marketplace/data/panel.json`: referencia do painel fixo (channelId/messageId).

Formato basico do anuncio (Listing):
- `id`: UUID.
- `type`: `sell` ou `buy`.
- `sellerId`, `sellerName`: usuario que publicou o anuncio.
- `itemName`, `category`, `price`, `description`.
- `imageUrl`: pode ser URL direta ou `attachment://...` quando anexada ao anuncio.
- `channelId`, `messageId`: mensagem publicada no canal do mercado.
- `status`: `active`, `closed`, `expired`.
- `createdAt`, `expiresAt`, `closedAt`.

## Painel do Mercado (Mensagem Fixa)

No boot (`ready.js`), o bot:
1. Sincroniza os slash commands na guild.
2. Publica (ou edita) o painel fixo no canal `MARKET_CHANNEL_ID`.

O painel fixo evita depender do cache do Discord para slash command e garante que o mercado esteja sempre acessivel por botoes.

## Criacao de Anuncio (Venda/Compra)

Fluxo:
1. Usuario clica `Vender Item` ou `Comprar Item` no painel.
2. Bot manda um select menu para escolher a categoria.
3. Bot abre modal com `itemName`, `price`, `description` e `imageUrl` (opcional).
4. Bot salva no `listings.json` e publica o embed no canal do mercado.
5. Bot salva `channelId/messageId` do anuncio publicado.

## Diferenca Compra x Venda

O campo `type` determina:
- titulo e badge do embed (`VENDO ...` ou `COMPRO ...`).
- cor/acento do embed.
- texto do botao principal (`Tenho Interesse` vs `Tenho o Item`).
- textos do DM e do embed da conversa.

## Conversa Privada (Negociacao)

Quando alguem clica no botao principal do anuncio:
1. Bot verifica se ja existe conversa aberta para (listingId + buyerId). Se existir, reaproveita.
2. Bot cria um canal privado (GuildText) na categoria:
   - `NEGOTIATION_CATEGORY_ID` se configurada
   - caso contrario: mesma categoria do canal do mercado
3. Permissoes do canal:
   - `@everyone`: sem acesso
   - dono do anuncio + interessado: acesso total de chat
   - bot: gerenciar canal e enviar mensagens
4. Bot posta um card de abertura com resumo do anuncio e botao `Encerrar conversa`.
5. Ao encerrar, o bot deleta o canal apos alguns segundos e marca a conversa como `closed` no store.

## Imagem do Item (Ctrl+V / Print)

Como o Discord nao permite upload em modal, o sistema usa um fluxo em duas etapas:
1. Depois de criar o anuncio, o bot mostra um botao `Adicionar imagem` (ephemeral).
2. O dono do anuncio cola um print no canal com Ctrl+V em ate 2 minutos.
3. O bot baixa a imagem e **reanexa a imagem na mensagem original do anuncio**, usando `attachment://...` no embed.
4. O bot tenta apagar a mensagem do print (para manter o canal limpo).

Requisitos:
- O bot precisa do intent `Message Content` para processar o evento `messageCreate` em mensagens comuns.
- Para apagar a mensagem do print, o bot precisa de permissao `Gerenciar Mensagens` no canal.

## Expiracao e Limpeza (Jobs)

Roda a cada `EXPIRATION_INTERVAL_MS`:
- Expiracao: anuncios `active` com `expiresAt` no passado viram `expired` e o embed e atualizado (encerrado).
- Limpeza: anuncios `closed/expired` com `closedAt` (ou fallback em `createdAt`) mais antigos que `CLOSED_DELETE_HOURS` (15h) sao deletados:
  - apaga a mensagem do anuncio no canal (se existir)
  - remove do `listings.json`

## Permissoes Necessarias do Bot

Para funcionar sem erros, o bot precisa:
- `Ver Canais` e `Enviar Mensagens` no canal do mercado.
- `Gerenciar Canais` para criar canais privados de negociacao.
- `Gerenciar Mensagens` (opcional) para apagar a mensagem do print ao adicionar imagem.
- `Embed Links` e `Anexar Arquivos` para embeds e imagens.

## Variaveis de Ambiente

- `DISCORD_TOKEN`: token do bot.
- `CLIENT_ID`: opcional; se vazio, o bot usa o application id do proprio client.
- `GUILD_ID`: guild onde os comandos sao sincronizados.
- `MARKET_CHANNEL_ID`: canal onde anuncios e o painel fixo sao publicados.
- `NEGOTIATION_CATEGORY_ID`: categoria onde as conversas privadas sao criadas (opcional).
