const { Client, Collection, GatewayIntentBits } = require('discord.js');
const { env } = require('./config/env');
const { loadCommands } = require('./handlers/commandHandler');
const { loadEvents } = require('./handlers/eventHandler');

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
  ],
});

client.commands = new Collection();

async function bootstrap() {
  loadCommands(client);
  loadEvents(client);
  await client.login(env.DISCORD_TOKEN);
}

bootstrap().catch((error) => {
  console.error('[Mercado Drakoria] Falha ao iniciar:', error);
  process.exit(1);
});
