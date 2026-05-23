const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const dataDir = path.resolve(__dirname, '..', '..', 'data');
const dataFile = path.join(dataDir, 'listings.json');

function ensureStore() {
  if (!fs.existsSync(dataDir)) {
    fs.mkdirSync(dataDir, { recursive: true });
  }
  if (!fs.existsSync(dataFile)) {
    fs.writeFileSync(dataFile, JSON.stringify({ listings: [] }, null, 2), 'utf8');
  }
}

function readStore() {
  ensureStore();
  const raw = fs.readFileSync(dataFile, 'utf8');
  const parsed = JSON.parse(raw || '{"listings":[]}');
  if (!Array.isArray(parsed.listings)) {
    return { listings: [] };
  }
  return parsed;
}

function writeStore(store) {
  ensureStore();
  fs.writeFileSync(dataFile, JSON.stringify(store, null, 2), 'utf8');
}

function createListing(input) {
  const store = readStore();
  const now = new Date().toISOString();
  const listing = {
    id: crypto.randomUUID(),
    type: input.type || 'sell',
    sellerId: input.sellerId,
    sellerName: input.sellerName,
    itemName: input.itemName,
    category: input.category,
    price: input.price,
    description: input.description || '',
    imageUrl: input.imageUrl || '',
    guildId: input.guildId,
    channelId: input.channelId || null,
    messageId: input.messageId || null,
    status: input.status || 'active',
    createdAt: input.createdAt || now,
    expiresAt: input.expiresAt,
  };
  store.listings.push(listing);
  writeStore(store);
  return listing;
}

function updateListing(id, updater) {
  const store = readStore();
  const index = store.listings.findIndex((listing) => listing.id === id);
  if (index === -1) return null;
  const updated = updater({ ...store.listings[index] });
  store.listings[index] = updated;
  writeStore(store);
  return updated;
}

function findListingById(id) {
  const store = readStore();
  return store.listings.find((listing) => listing.id === id) || null;
}

function findActiveListingsBySeller(guildId, sellerId, limit = 5) {
  const store = readStore();
  return store.listings
    .filter((listing) => listing.guildId === guildId && listing.sellerId === sellerId && listing.status === 'active')
    .sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt))
    .slice(0, limit);
}

function findExpiredActiveListings(limit = 25) {
  const now = Date.now();
  const store = readStore();
  return store.listings
    .filter((listing) => listing.status === 'active' && Date.parse(listing.expiresAt) <= now)
    .slice(0, limit);
}

module.exports = {
  createListing,
  updateListing,
  findListingById,
  findActiveListingsBySeller,
  findExpiredActiveListings,
};
