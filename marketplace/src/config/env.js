const path = require('path');
const dotenv = require('dotenv');

dotenv.config({ path: path.resolve(__dirname, '..', '..', '.env') });
dotenv.config({ path: path.resolve(__dirname, '..', '..', '..', '.env') });

const required = ['DISCORD_TOKEN', 'GUILD_ID'];

for (const key of required) {
  if (!process.env[key]) {
    throw new Error(`Variavel de ambiente obrigatoria ausente: ${key}`);
  }
}

const env = {
  DISCORD_TOKEN: process.env.DISCORD_TOKEN,
  CLIENT_ID: process.env.CLIENT_ID || null,
  GUILD_ID: process.env.GUILD_ID,
  MARKET_CHANNEL_ID: process.env.MARKET_CHANNEL_ID || null,
  NEGOTIATION_CATEGORY_ID: process.env.NEGOTIATION_CATEGORY_ID || null,
};

module.exports = { env };
