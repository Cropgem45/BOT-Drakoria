const { ActionRowBuilder, ButtonBuilder, ButtonStyle } = require('discord.js');
const { ids } = require('../../utils/componentIds');

function marketPanelButtons() {
  return new ActionRowBuilder().addComponents(
    new ButtonBuilder()
      .setCustomId(ids.createListing)
      .setLabel('Vender Item')
      .setStyle(ButtonStyle.Primary),
    new ButtonBuilder()
      .setCustomId(ids.createBuying)
      .setLabel('Comprar Item')
      .setStyle(ButtonStyle.Success),
    new ButtonBuilder()
      .setCustomId(ids.myListings)
      .setLabel('Meus Anuncios')
      .setStyle(ButtonStyle.Secondary),
  );
}

module.exports = { marketPanelButtons };
