const { ActionRowBuilder, ButtonBuilder, ButtonStyle } = require('discord.js');
const { ids } = require('../../utils/componentIds');

function negotiationButtons(conversationId) {
  return new ActionRowBuilder().addComponents(
    new ButtonBuilder()
      .setCustomId(ids.closeNegotiation(conversationId))
      .setLabel('Encerrar conversa')
      .setStyle(ButtonStyle.Danger),
  );
}

module.exports = { negotiationButtons };
