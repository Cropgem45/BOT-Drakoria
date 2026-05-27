const { categories } = require('../config/constants');

function categoryText(category) {
  const found = categories[category];
  return found ? `${found.emoji} ${found.label}` : 'Outros';
}

function compactTimeLeft(expiresAt) {
  const expiresMs = new Date(expiresAt).getTime();
  if (!Number.isFinite(expiresMs)) return 'tempo indisponivel';
  const ms = expiresMs - Date.now();
  if (ms <= 0) return 'expirado';
  const unix = Math.floor(expiresMs / 1000);
  const hours = Math.ceil(ms / 1000 / 60 / 60);
  return `${hours}h restantes (${discordRelativeTime(unix)})`;
}

function discordRelativeTime(unix) {
  return `<t:${unix}:R>`;
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
  discordRelativeTime,
  displayName,
  cleanText,
};
