const { EmbedBuilder } = require('discord.js');
const { theme } = require('../config/theme');
const { categoryText, compactTimeLeft } = require('./formatters');

function marketPanelEmbed() {
  return new EmbedBuilder()
    .setColor(theme.colors.gold)
    .setTitle('Mercado Drakoria')
    .setDescription(
      [
        'Venda itens ou anuncie o que voce esta procurando.',
        '',
        '**Escolha uma acao abaixo.**',
      ].join('\n'),
    )
    .setFooter({ text: theme.footer })
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
        intro: 'Um jogador esta procurando este item. Se voce tem, abra uma conversa.',
        priceLabel: '💰 Pagamento',
        ownerLabel: '👤 Comprador',
        actionHint: 'Clique em **Tenho o Item** para negociar com o comprador.',
      }
    : {
        badge: '🛒 ANUNCIO DE VENDA',
        title: `VENDO ${listing.itemName.toUpperCase()}`,
        intro: 'Item disponivel para negociacao no Mercado Drakoria.',
        priceLabel: '💰 Preco',
        ownerLabel: '👤 Vendedor',
        actionHint: 'Clique em **Tenho Interesse** para negociar com o vendedor.',
      };
  const title = closed
    ? 'ANUNCIO ENCERRADO'
    : mode.title;
  const description = listing.description || 'Sem descricao adicional.';

  const embed = new EmbedBuilder()
    .setColor(closed ? theme.colors.closed : accent)
    .setTitle(title)
    .setDescription(
      closed
        ? '⛔ **Este anuncio nao esta mais disponivel.**'
        : [
            `**${mode.badge}**`,
            mode.intro,
            '',
            mode.actionHint,
          ].join('\n'),
    )
    .addFields(
      {
        name: mode.priceLabel,
        value: `**${listing.price}**`,
        inline: true,
      },
      {
        name: mode.ownerLabel,
        value: `**${listing.sellerName}**`,
        inline: true,
      },
      {
        name: '📂 Categoria',
        value: `**${category}**`,
        inline: true,
      },
      {
        name: '⏳ Tempo restante',
        value: closed ? '**Encerrado**' : `**${compactTimeLeft(listing.expiresAt)}**`,
        inline: true,
      },
      {
        name: '📜 Descricao do anuncio',
        value: [
          '```md',
          description.slice(0, 900),
          '```',
        ].join('\n'),
        inline: false,
      },
    )
    .setFooter({ text: `${theme.footer} • ${isBuying ? 'Compra' : 'Venda'} segura via Discord` })
    .setTimestamp();

  if (listing.imageUrl) {
    embed.setImage(listing.imageUrl);
  } else {
    embed.addFields({
      name: '🖼️ Imagem',
      value: '*Sem imagem adicionada.*',
      inline: false,
    });
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
