const ids = {
  createListing: 'market:create',
  createBuying: 'market:create-buying',
  myListings: 'market:mine',
  categorySelect: (type = 'sell') => `market:category:${type}`,
  listingModal: (type, category) => `market:modal:${type}:${category}`,
  interest: (listingId) => `market:interest:${listingId}`,
  close: (listingId) => `market:close:${listingId}`,
  closeMine: (listingId) => `market:mine:close:${listingId}`,
  addImage: (listingId) => `market:image:add:${listingId}`,
  closeNegotiation: (conversationId) => `market:negotiation:close:${conversationId}`,
};

function parts(customId) {
  return customId.split(':');
}

module.exports = { ids, parts };
