const { ActionRowBuilder, ButtonBuilder, ButtonStyle } = require('discord.js');
const { ids } = require('../../utils/componentIds');

function createdListingButtons(listingId) {
  return new ActionRowBuilder().addComponents(
    new ButtonBuilder()
      .setCustomId(ids.addImage(listingId))
      .setLabel('Adicionar imagem')
      .setStyle(ButtonStyle.Secondary),
  );
}

module.exports = { createdListingButtons };
