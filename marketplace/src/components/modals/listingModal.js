const {
  ActionRowBuilder,
  ModalBuilder,
  TextInputBuilder,
  TextInputStyle,
} = require('discord.js');
const { ids } = require('../../utils/componentIds');

function listingModal(type, category) {
  const isBuying = type === 'buy';

  return new ModalBuilder()
    .setCustomId(ids.listingModal(type, category))
    .setTitle(isBuying ? 'Criar compra' : 'Criar venda')
    .addComponents(
      new ActionRowBuilder().addComponents(
        new TextInputBuilder()
          .setCustomId('itemName')
          .setLabel('Nome do item')
          .setPlaceholder(isBuying ? 'Ex: Diamantes x64' : 'Ex: Espada Netherita Full')
          .setStyle(TextInputStyle.Short)
          .setMaxLength(80)
          .setRequired(true),
      ),
      new ActionRowBuilder().addComponents(
        new TextInputBuilder()
          .setCustomId('price')
          .setLabel(isBuying ? 'Quanto voce paga?' : 'Preco')
          .setPlaceholder(isBuying ? 'Ex: Pago 20.000 coins' : 'Ex: 50.000 coins')
          .setStyle(TextInputStyle.Short)
          .setMaxLength(40)
          .setRequired(true),
      ),
      new ActionRowBuilder().addComponents(
        new TextInputBuilder()
          .setCustomId('description')
          .setLabel('Descricao opcional')
          .setPlaceholder(isBuying ? 'Ex: Aceito negociar quantidade' : 'Ex: Boa pra PvP')
          .setStyle(TextInputStyle.Paragraph)
          .setMaxLength(300)
          .setRequired(false),
      ),
      new ActionRowBuilder().addComponents(
        new TextInputBuilder()
          .setCustomId('imageUrl')
          .setLabel('Link da imagem opcional')
          .setPlaceholder('Opcional. Melhor: crie e use Adicionar imagem depois.')
          .setStyle(TextInputStyle.Short)
          .setMaxLength(300)
          .setRequired(false),
      ),
    );
}

module.exports = { listingModal };
