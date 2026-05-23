const LISTING_DURATION_HOURS = 48;
const EXPIRATION_INTERVAL_MS = 5 * 60 * 1000;

const categories = {
  weapons: { label: 'Armas', emoji: '⚔️' },
  resources: { label: 'Recursos', emoji: '💎' },
  rares: { label: 'Raros', emoji: '🐎' },
  other: { label: 'Outros', emoji: '📦' },
};

module.exports = {
  LISTING_DURATION_HOURS,
  EXPIRATION_INTERVAL_MS,
  categories,
};
