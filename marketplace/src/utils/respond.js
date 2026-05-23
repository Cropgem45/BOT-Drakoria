const { MessageFlags } = require('discord.js');

async function sendEphemeral(interaction, payload) {
  const response = {
    ...payload,
    flags: MessageFlags.Ephemeral,
  };

  try {
    if (interaction.deferred) {
      return await interaction.editReply(response);
    }
    if (interaction.replied) {
      return await interaction.followUp(response);
    }
    return await interaction.reply(response);
  } catch (error) {
    if ([40060, 10062].includes(error.code)) {
      return null;
    }
    throw error;
  }
}

module.exports = { sendEphemeral };
