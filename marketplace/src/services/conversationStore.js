const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const dataDir = path.resolve(__dirname, '..', '..', 'data');
const dataFile = path.join(dataDir, 'conversations.json');

function ensureStore() {
  if (!fs.existsSync(dataDir)) {
    fs.mkdirSync(dataDir, { recursive: true });
  }
  if (!fs.existsSync(dataFile)) {
    fs.writeFileSync(dataFile, JSON.stringify({ conversations: [] }, null, 2), 'utf8');
  }
}

function readStore() {
  ensureStore();
  const parsed = JSON.parse(fs.readFileSync(dataFile, 'utf8') || '{"conversations":[]}');
  return Array.isArray(parsed.conversations) ? parsed : { conversations: [] };
}

function writeStore(store) {
  ensureStore();
  fs.writeFileSync(dataFile, JSON.stringify(store, null, 2), 'utf8');
}

function createConversation(input) {
  const store = readStore();
  const conversation = {
    id: crypto.randomUUID(),
    listingId: input.listingId,
    guildId: input.guildId,
    channelId: input.channelId,
    sellerId: input.sellerId,
    buyerId: input.buyerId,
    status: 'open',
    createdAt: new Date().toISOString(),
    closedAt: null,
  };
  store.conversations.push(conversation);
  writeStore(store);
  return conversation;
}

function findOpenConversation(listingId, buyerId) {
  const store = readStore();
  return store.conversations.find((conversation) => (
    conversation.listingId === listingId
    && conversation.buyerId === buyerId
    && conversation.status === 'open'
  )) || null;
}

function findConversationById(id) {
  const store = readStore();
  return store.conversations.find((conversation) => conversation.id === id) || null;
}

function closeConversation(id) {
  const store = readStore();
  const index = store.conversations.findIndex((conversation) => conversation.id === id);
  if (index === -1) return null;

  store.conversations[index] = {
    ...store.conversations[index],
    status: 'closed',
    closedAt: new Date().toISOString(),
  };
  writeStore(store);
  return store.conversations[index];
}

module.exports = {
  createConversation,
  findOpenConversation,
  findConversationById,
  closeConversation,
};
