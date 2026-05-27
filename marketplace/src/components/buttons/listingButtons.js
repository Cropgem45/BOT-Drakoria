const { ActionRowBuilder, ButtonBuilder, ButtonStyle } = require('discord.js');
const { ids } = require('../../utils/componentIds');

function listingButtons(listingId, disabled = false, type = 'sell') {
  return new ActionRowBuilder().addComponents(
    new ButtonBuilder()
      .setCustomId(ids.interest(listingId))
      .setLabel(type === 'buy' ? 'Tenho o Item' : 'Tenho Interesse')
      .setStyle(ButtonStyle.Success)
      .setDisabled(disabled),
    new ButtonBuilder()
      .setCustomId(ids.close(listingId))
      .setLabel('Encerrar Anuncio')
      .setStyle(ButtonStyle.Danger)
      .setDisabled(disabled),
  );
}

function myListingCloseButtons(listings) {
  const row = new ActionRowBuilder();
  for (const [index, listing] of listings.slice(0, 5).entries()) {
    row.addComponents(
      new ButtonBuilder()
        .setCustomId(ids.closeMine(listing.id))
        .setLabel(`Encerrar ${index + 1}`)
        .setStyle(ButtonStyle.Danger),
    );
  }
  return row.components.length ? [row] : [];
}

module.exports = { listingButtons, myListingCloseButtons };
