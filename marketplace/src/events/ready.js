const { ActivityType, REST, Routes } = require('discord.js');
const { env } = require('../config/env');
const { startExpirationHandler } = require('../handlers/expirationHandler');
const { publishMarketPanel } = require('../services/panelService');

module.exports = {
  name: 'clientReady',
  once: true,
  async execute(client) {
    const rest = new REST({ version: '10' }).setToken(env.DISCORD_TOKEN);
    const commands = client.commands.map((command) => command.data.toJSON());

    const applicationId = env.CLIENT_ID || client.application.id;
    const guildIds = new Set([env.GUILD_ID, ...client.guilds.cache.map((guild) => guild.id)]);

    for (const guildId of guildIds) {
      await rest.put(
        Routes.applicationGuildCommands(applicationId, guildId),
        { body: commands },
      );
      console.log(`[Mercado Drakoria] Comandos sincronizados na guild ${guildId}.`);
    }

    client.user.setActivity('Mercado Drakoria', { type: ActivityType.Watching });
    await publishMarketPanel(client);
    startExpirationHandler(client);
    console.log(`[Mercado Drakoria] Online como ${client.user.tag}`);
  },
};
