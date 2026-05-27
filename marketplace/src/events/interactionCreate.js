const { ids, parts } = require('../utils/componentIds');
const { categoryMenu } = require('../components/menus/categoryMenu');
const { listingModal } = require('../components/modals/listingModal');
const listingService = require('../services/listingService');
const { deferEphemeral, sendEphemeral } = require('../utils/respond');

module.exports = {
  name: 'interactionCreate',
  async execute(interaction) {
    try {
      if (interaction.isChatInputCommand()) {
        const command = interaction.client.commands.get(interaction.commandName);
        if (!command) return;
        await command.execute(interaction);
        return;
      }

      if (interaction.isButton()) {
        if (interaction.customId === ids.createListing) {
          await deferEphemeral(interaction);
          await sendEphemeral(interaction, {
            content: 'Escolha a categoria do item que voce quer vender.',
            components: [categoryMenu('sell')],
          });
          return;
        }

        if (interaction.customId === ids.createBuying) {
          await deferEphemeral(interaction);
          await sendEphemeral(interaction, {
            content: 'Escolha a categoria do item que voce quer comprar.',
            components: [categoryMenu('buy')],
          });
          return;
        }

        if (interaction.customId === ids.myListings) {
          await listingService.showMyListings(interaction);
          return;
        }

        const [scope, action, detail, listingId] = parts(interaction.customId);

        if (scope === 'market' && action === 'interest') {
          await listingService.sendInterest(interaction, detail);
          return;
        }

        if (scope === 'market' && action === 'close') {
          await listingService.closeListing(interaction, detail);
          return;
        }

        if (scope === 'market' && action === 'mine' && detail === 'close') {
          await listingService.closeListing(interaction, listingId);
          return;
        }

        if (scope === 'market' && action === 'image' && detail === 'add') {
          await listingService.requestListingImage(interaction, listingId);
          return;
        }

        if (scope === 'market' && action === 'negotiation' && detail === 'close') {
          await listingService.closeConversation(interaction, listingId);
          return;
        }
        await sendUnhandledMarketInteraction(interaction);
        return;
      }

      if (interaction.isStringSelectMenu()) {
        const [scope, action, type] = parts(interaction.customId);
        if (scope === 'market' && action === 'category') {
          await interaction.showModal(listingModal(type || 'sell', interaction.values[0]));
          return;
        }
        await sendUnhandledMarketInteraction(interaction);
        return;
      }

      if (interaction.isModalSubmit()) {
        const [scope, action, type, category] = parts(interaction.customId);
        if (scope === 'market' && action === 'modal') {
          await listingService.createListing(interaction, category, type || 'sell');
          return;
        }
        await sendUnhandledMarketInteraction(interaction);
      }
    } catch (error) {
      if ([40060, 10062].includes(error.code)) {
        console.warn(`[Mercado Drakoria] Interacao ${interaction.id} indisponivel; erro ignorado.`);
        return;
      }

      console.error('[Mercado Drakoria] Erro em interacao:', error);
      await sendEphemeral(interaction, {
        content: 'Algo deu errado ao processar esta acao.',
      }).catch(() => null);
    }
  },
};

async function sendUnhandledMarketInteraction(interaction) {
  const customId = interaction.customId || '';
  if (!customId.startsWith('market:')) return;

  console.warn(`[Mercado Drakoria] Componente sem handler: ${customId}`);
  await sendEphemeral(interaction, {
    content: 'Este botao do mercado esta desatualizado. Use o painel mais recente do Mercado Drakoria.',
  });
}
