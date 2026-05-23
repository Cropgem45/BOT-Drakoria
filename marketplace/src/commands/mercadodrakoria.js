const { SlashCommandBuilder } = require('discord.js');
const { marketPanelButtons } = require('../components/buttons/marketButtons');
const { marketPanelEmbed } = require('../utils/embeds');
const { sendEphemeral } = require('../utils/respond');

module.exports = {
  data: new SlashCommandBuilder()
    .setName('mercadodrakoria')
    .setDescription('Abre o painel do Mercado Drakoria.'),

  async execute(interaction) {
    await sendEphemeral(interaction, {
      embeds: [marketPanelEmbed()],
      components: [marketPanelButtons()],
    });
  },
};
