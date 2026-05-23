const { categories } = require('../config/constants');

function categoryText(category) {
  const found = categories[category];
  return found ? `${found.emoji} ${found.label}` : 'Outros';
}

function compactTimeLeft(expiresAt) {
  const ms = new Date(expiresAt).getTime() - Date.now();
  if (ms <= 0) return 'expirado';
  const hours = Math.ceil(ms / 1000 / 60 / 60);
  return `${hours}h restantes`;
}

function displayName(user) {
  return user.globalName || user.username;
}

function cleanText(value, fallback = 'Nao informado') {
  const text = String(value || '').trim();
  return text || fallback;
}

module.exports = {
  categoryText,
  compactTimeLeft,
  displayName,
  cleanText,
};
