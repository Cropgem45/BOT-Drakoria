const { EmbedBuilder } = require('discord.js');
const { theme } = require('../config/theme');
const { categoryText, compactTimeLeft } = require('./formatters');

function marketPanelEmbed() {
  return new EmbedBuilder()
    .setColor(theme.colors.gold)
    .setTitle('🛒 Mercado Drakoria')
    .setDescription(
      [
        'Compra e venda de itens direto no Discord, com conversa privada.',
        '',
        'Escolha uma acao abaixo:',
        '',
        '🟨 **Vender Item**: publique um anuncio de venda',
        '🟦 **Comprar Item**: publique um anuncio de compra',
        '📦 **Meus Anuncios**: gerencie seus anuncios',
      ].join('\n'),
    )
    .setFooter({ text: `${theme.footer} • Painel do Mercado` })
    .setTimestamp();
}

function listingEmbed(listing, { closed = false } = {}) {
  const category = categoryText(listing.category);
  const isBuying = listing.type === 'buy';
  const accent = isBuying ? theme.colors.buy : theme.colors.sell;
  const mode = isBuying
    ? {
        badge: '🔎 ANUNCIO DE COMPRA',
        title: `COMPRO ${listing.itemName.toUpperCase()}`,
        intro: 'Se voce tem o item, abra uma conversa e combine a troca.',
        priceLabel: 'Pagamento',
        ownerLabel: 'Comprador',
        actionHint: 'Clique em **Tenho o Item** para negociar.',
      }
    : {
        badge: '🛒 ANUNCIO DE VENDA',
        title: `VENDO ${listing.itemName.toUpperCase()}`,
        intro: 'Item disponivel para negociacao no Mercado Drakoria.',
        priceLabel: 'Preco',
        ownerLabel: 'Vendedor',
        actionHint: 'Clique em **Tenho Interesse** para negociar.',
      };
  const title = closed
    ? 'ANUNCIO ENCERRADO'
    : mode.title;
  const description = (listing.description || '').trim();

  const embed = new EmbedBuilder()
    .setColor(closed ? theme.colors.closed : accent)
    .setTitle(title)
    .setDescription(
      closed
        ? '⛔ **Este anuncio nao esta mais disponivel.**'
        : [
            `**${mode.badge}**`,
            '',
            `💰 **${mode.priceLabel}:** **${listing.price}**`,
            `👤 **${mode.ownerLabel}:** **${listing.sellerName}**`,
            '',
            `📂 **Categoria:** **${category}**`,
            `⏳ **Tempo:** **${compactTimeLeft(listing.expiresAt)}**`,
            description ? '' : '',
            description ? `📝 **Descricao:**\n> ${description.slice(0, 350).replace(/\n/g, '\n> ')}` : '',
            '',
            `_${mode.actionHint}_`,
          ].filter(Boolean).join('\n'),
    )
    .addFields(
      closed
        ? []
        : [
            {
              name: 'Atalho',
              value: isBuying ? '📦 Tenho o Item' : '💬 Tenho Interesse',
              inline: true,
            },
            {
              name: 'Status',
              value: '🟢 Ativo',
              inline: true,
            },
          ],
    )
    .setFooter({ text: `${theme.footer} • ${isBuying ? 'Compra' : 'Venda'} segura via Discord` })
    .setTimestamp();

  if (listing.imageUrl) {
    embed.setImage(listing.imageUrl);
  }

  return embed;
}

function createdEmbed(listing) {
  const isBuying = listing.type === 'buy';

  return new EmbedBuilder()
    .setColor(theme.colors.success)
    .setTitle(isBuying ? 'Compra publicada' : 'Venda publicada')
    .setDescription(`Seu anuncio **${listing.itemName}** foi enviado ao Mercado Drakoria.`)
    .setFooter({ text: theme.footer })
    .setTimestamp();
}

function myListingsEmbed(listings) {
  const description = listings.length
    ? listings.map((listing, index) => {
        return [
          `**${index + 1}. ${categoryText(listing.category).split(' ')[0]} ${listing.itemName}**`,
          `Tipo: ${listing.type === 'buy' ? 'Compra' : 'Venda'}`,
          `Valor: ${listing.price}`,
          `Tempo: ${compactTimeLeft(listing.expiresAt)}`,
        ].join('\n');
      }).join('\n\n')
    : 'Voce nao possui anuncios ativos no momento.';

  const embed = new EmbedBuilder()
    .setColor(theme.colors.gold)
    .setTitle('Seus anuncios')
    .setDescription(description)
    .setFooter({ text: theme.footer })
    .setTimestamp();

  return embed;
}

function dmInterestEmbed(listing, buyer) {
  const isBuying = listing.type === 'buy';

  return new EmbedBuilder()
    .setColor(isBuying ? theme.colors.buy : theme.colors.sell)
    .setTitle(isBuying ? '📦 Alguem tem o item que voce procura' : '💬 Novo interessado no seu item')
    .setDescription(
      [
        isBuying
          ? `${buyer} disse que pode vender para voce:`
          : `${buyer} demonstrou interesse em comprar:`,
        '',
        `**${listing.itemName}**`,
      ].join('\n'),
    )
    .setFooter({ text: theme.footer })
    .setTimestamp();
}

function negotiationEmbed(listing, buyer) {
  const isBuying = listing.type === 'buy';

  return new EmbedBuilder()
    .setColor(isBuying ? theme.colors.buy : theme.colors.sell)
    .setTitle(isBuying ? '📦 Conversa de Compra Iniciada' : '💬 Conversa de Venda Iniciada')
    .setDescription(
      isBuying
        ? 'O comprador procura este item. O fornecedor pode combinar quantidade, valor e entrega por aqui.'
        : 'O vendedor oferece este item. Cliente e vendedor podem combinar valor e entrega por aqui.',
    )
    .addFields(
      {
        name: '📌 Item',
        value: `**${listing.itemName}**`,
        inline: true,
      },
      {
        name: isBuying ? '💰 Pagamento anunciado' : '💰 Valor anunciado',
        value: `**${listing.price}**`,
        inline: true,
      },
      {
        name: isBuying ? '👤 Comprador' : '👤 Vendedor',
        value: `<@${listing.sellerId}>`,
        inline: true,
      },
      {
        name: isBuying ? '📦 Fornecedor' : '🤝 Cliente',
        value: `${buyer}`,
        inline: true,
      },
      {
        name: '📜 Descricao do anuncio',
        value: [
          '```md',
          (listing.description || 'Sem descricao adicional.').slice(0, 900),
          '```',
        ].join('\n'),
        inline: false,
      },
    )
    .setFooter({ text: `${theme.footer} - Conversa privada` })
    .setTimestamp();

  if (listing.imageUrl) {
    embed.setImage(listing.imageUrl);
  }

  return embed;
}

module.exports = {
  marketPanelEmbed,
  listingEmbed,
  createdEmbed,
  myListingsEmbed,
  dmInterestEmbed,
  negotiationEmbed,
};
