const { MessageFlags } = require('discord.js');

async function deferEphemeral(interaction) {
  if (interaction.deferred || interaction.replied) return;

  try {
    await interaction.deferReply({ flags: MessageFlags.Ephemeral });
  } catch (error) {
    if ([40060, 10062].includes(error.code)) {
      return;
    }
    throw error;
  }
}

async function sendEphemeral(interaction, payload) {
  const initialResponse = {
    ...payload,
    flags: MessageFlags.Ephemeral,
  };

  try {
    if (interaction.deferred) {
      return await interaction.editReply(payload);
    }
    if (interaction.replied) {
      return await interaction.followUp(initialResponse);
    }
    return await interaction.reply(initialResponse);
  } catch (error) {
    if ([40060, 10062].includes(error.code)) {
      return null;
    }
    throw error;
  }
}

module.exports = { deferEphemeral, sendEphemeral };
