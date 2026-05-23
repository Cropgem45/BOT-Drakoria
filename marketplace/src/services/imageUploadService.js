const path = require('path');
const { AttachmentBuilder } = require('discord.js');
const { updateListing } = require('./listingStore');
const { listingEmbed } = require('../utils/embeds');
const { listingButtons } = require('../components/buttons/listingButtons');

const pendingUploads = new Map();
const ttlMs = 2 * 60 * 1000;

function startImageUpload({ userId, guildId, channelId, listingId }) {
  const key = keyFor(userId, guildId);
  const previous = pendingUploads.get(key);
  if (previous?.timeout) {
    clearTimeout(previous.timeout);
  }

  const timeout = setTimeout(() => pendingUploads.delete(key), ttlMs);
  pendingUploads.set(key, {
    userId,
    guildId,
    channelId,
    listingId,
    timeout,
  });
}

async function handleImageMessage(message) {
  if (!message.guild || message.author.bot) return false;

  const pending = pendingUploads.get(keyFor(message.author.id, message.guild.id));
  if (!pending) return false;
  if (pending.channelId !== message.channelId) return false;

  const attachment = message.attachments.find((file) => isImageAttachment(file));
  if (!attachment) {
    await message.reply('Envie uma imagem anexada ou cole o print com Ctrl+V.').catch(() => null);
    return true;
  }

  clearTimeout(pending.timeout);
  pendingUploads.delete(keyFor(message.author.id, message.guild.id));

  const image = await downloadAttachment(attachment.url);
  const extension = extensionFor(attachment.name || attachment.url);
  const fileName = `produto-${pending.listingId.slice(0, 8)}${extension}`;
  const imageRef = `attachment://${fileName}`;

  const listing = updateListing(pending.listingId, (current) => ({
    ...current,
    imageUrl: imageRef,
    imageFileName: fileName,
  }));

  if (!listing) return true;
  const updated = await editListingMessage(message.client, listing, image, fileName);
  if (updated) {
    await message.delete().catch(() => null);
    await message.author.send(`Imagem adicionada ao anuncio **${listing.itemName}**.`).catch(() => null);
  } else {
    await message.reply('Nao consegui atualizar a mensagem original do anuncio.').catch(() => null);
  }
  return true;
}

async function editListingMessage(client, listing, image, fileName) {
  if (!listing.channelId || !listing.messageId) return false;

  const channel = await client.channels.fetch(listing.channelId).catch(() => null);
  if (!channel || !channel.isTextBased()) return false;

  const announcement = await channel.messages.fetch(listing.messageId).catch(() => null);
  if (!announcement) return false;

  await announcement.edit({
    embeds: [listingEmbed(listing)],
    components: [listingButtons(listing.id, false, listing.type)],
    files: [new AttachmentBuilder(image, { name: fileName })],
  });
  return true;
}

function isImageAttachment(attachment) {
  if (attachment.contentType?.startsWith('image/')) return true;
  return /\.(png|jpe?g|gif|webp)$/i.test(attachment.name || '');
}

function keyFor(userId, guildId) {
  return `${guildId}:${userId}`;
}

async function downloadAttachment(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Falha ao baixar imagem: ${response.status}`);
  }
  return Buffer.from(await response.arrayBuffer());
}

function extensionFor(name) {
  const extension = path.extname(String(name).split('?')[0]).toLowerCase();
  if (['.png', '.jpg', '.jpeg', '.gif', '.webp'].includes(extension)) {
    return extension;
  }
  return '.png';
}

module.exports = {
  startImageUpload,
  handleImageMessage,
};
