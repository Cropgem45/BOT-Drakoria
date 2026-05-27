const { EXPIRATION_INTERVAL_MS, CLOSED_DELETE_HOURS } = require('../config/constants');
const { editListingAsActive, editListingAsClosed } = require('../services/listingService');
const {
  findActiveListings,
  findExpiredActiveListings,
  updateListing,
  findClosableListings,
  deleteListing,
} = require('../services/listingStore');

let started = false;

function startExpirationHandler(client) {
  if (started) return;
  started = true;

  const run = async () => {
    const expiredListings = findExpiredActiveListings(25);

    for (const listing of expiredListings) {
      const expiredListing = updateListing(listing.id, (current) => ({
        ...current,
        status: 'expired',
        closedAt: new Date().toISOString(),
      }));
      await editListingAsClosed(client, expiredListing);
    }

    const activeListings = findActiveListings(50);
    for (const listing of activeListings) {
      await editListingAsActive(client, listing);
    }

    const olderThanMs = CLOSED_DELETE_HOURS * 60 * 60 * 1000;
    const closable = findClosableListings(olderThanMs, 25);
    for (const listing of closable) {
      await deleteListingMessage(client, listing);
      deleteListing(listing.id);
    }
  };

  run().catch((error) => console.error('[Mercado Drakoria] Falha na expiracao:', error));
  setInterval(() => {
    run().catch((error) => console.error('[Mercado Drakoria] Falha na expiracao:', error));
  }, EXPIRATION_INTERVAL_MS);
}

async function deleteListingMessage(client, listing) {
  if (!listing || !listing.channelId || !listing.messageId) return;
  try {
    const channel = await client.channels.fetch(listing.channelId).catch(() => null);
    if (!channel || !channel.isTextBased()) return;
    const message = await channel.messages.fetch(listing.messageId).catch(() => null);
    if (!message) return;
    await message.delete().catch(() => null);
  } catch (error) {
    console.warn(`[Mercado Drakoria] Falha ao excluir anuncio ${listing.id}:`, error?.message || error);
  }
}

module.exports = { startExpirationHandler };
