const { EXPIRATION_INTERVAL_MS } = require('../config/constants');
const { editListingAsClosed } = require('../services/listingService');
const { findExpiredActiveListings, updateListing } = require('../services/listingStore');

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
      }));
      await editListingAsClosed(client, expiredListing);
    }
  };

  run().catch((error) => console.error('[Mercado Drakoria] Falha na expiracao:', error));
  setInterval(() => {
    run().catch((error) => console.error('[Mercado Drakoria] Falha na expiracao:', error));
  }, EXPIRATION_INTERVAL_MS);
}

module.exports = { startExpirationHandler };
