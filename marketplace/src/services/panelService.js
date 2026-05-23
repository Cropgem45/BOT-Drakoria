const fs = require('fs');
const path = require('path');
const { env } = require('../config/env');
const { marketPanelButtons } = require('../components/buttons/marketButtons');
const { marketPanelEmbed } = require('../utils/embeds');

const dataDir = path.resolve(__dirname, '..', '..', 'data');
const panelFile = path.join(dataDir, 'panel.json');

function readPanelState() {
  try {
    return JSON.parse(fs.readFileSync(panelFile, 'utf8'));
  } catch {
    return {};
  }
}

function writePanelState(state) {
  if (!fs.existsSync(dataDir)) {
    fs.mkdirSync(dataDir, { recursive: true });
  }
  fs.writeFileSync(panelFile, JSON.stringify(state, null, 2), 'utf8');
}

async function publishMarketPanel(client) {
  if (!env.MARKET_CHANNEL_ID) return;

  const channel = await client.channels.fetch(env.MARKET_CHANNEL_ID).catch(() => null);
  if (!channel || !channel.isTextBased()) return;

  const payload = {
    embeds: [marketPanelEmbed()],
    components: [marketPanelButtons()],
  };
  const state = readPanelState();

  if (state.channelId === channel.id && state.messageId) {
    const existing = await channel.messages.fetch(state.messageId).catch(() => null);
    if (existing) {
      await existing.edit(payload);
      console.log(`[Mercado Drakoria] Painel atualizado no canal ${channel.id}.`);
      return;
    }
  }

  const message = await channel.send(payload);
  writePanelState({ channelId: channel.id, messageId: message.id });
  console.log(`[Mercado Drakoria] Painel publicado no canal ${channel.id}.`);
}

module.exports = { publishMarketPanel };
