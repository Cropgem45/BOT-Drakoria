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
      const existingCommands = await rest.get(Routes.applicationGuildCommands(applicationId, guildId));
      const mergedCommands = mergeGuildCommands(existingCommands, commands);
      await rest.put(
        Routes.applicationGuildCommands(applicationId, guildId),
        { body: mergedCommands },
      );
      console.log(`[Mercado Drakoria] Comandos sincronizados na guild ${guildId}.`);
    }

    client.user.setActivity('Mercado Drakoria', { type: ActivityType.Watching });
    await publishMarketPanel(client);
    startExpirationHandler(client);
    console.log(`[Mercado Drakoria] Online como ${client.user.tag}`);
  },
};

function mergeGuildCommands(existingCommands, marketplaceCommands) {
  const commandMap = new Map();
  for (const command of existingCommands || []) {
    commandMap.set(command.name, sanitizeCommand(command));
  }
  for (const command of marketplaceCommands) {
    commandMap.set(command.name, command);
  }
  return [...commandMap.values()];
}

function sanitizeCommand(command) {
  const sanitized = {
    name: command.name,
    type: command.type,
    description: command.description,
  };

  for (const key of [
    'options',
    'default_member_permissions',
    'dm_permission',
    'nsfw',
    'integration_types',
    'contexts',
  ]) {
    if (command[key] !== undefined && command[key] !== null) {
      sanitized[key] = command[key];
    }
  }

  return sanitized;
}
