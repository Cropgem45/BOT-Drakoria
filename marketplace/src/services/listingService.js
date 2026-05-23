const {
  ChannelType,
  PermissionFlagsBits,
} = require('discord.js');
const { env } = require('../config/env');
const { LISTING_DURATION_HOURS } = require('../config/constants');
const {
  createListing: createListingRecord,
  updateListing,
  findListingById,
  findActiveListingsBySeller,
} = require('./listingStore');
const {
  createConversation,
  findOpenConversation,
  findConversationById,
  closeConversation: closeConversationRecord,
} = require('./conversationStore');
const { displayName, cleanText } = require('../utils/formatters');
const {
  listingEmbed,
  createdEmbed,
  myListingsEmbed,
  dmInterestEmbed,
  negotiationEmbed,
} = require('../utils/embeds');
const { listingButtons, myListingCloseButtons } = require('../components/buttons/listingButtons');
const { negotiationButtons } = require('../components/buttons/negotiationButtons');
const { createdListingButtons } = require('../components/buttons/createdListingButtons');
const { startImageUpload } = require('./imageUploadService');

async function createListing(interaction, category, type = 'sell') {
  if (!env.MARKET_CHANNEL_ID) {
    await interaction.reply({
      content: 'O canal do mercado ainda nao foi configurado em MARKET_CHANNEL_ID.',
      ephemeral: true,
    });
    return;
  }

  const itemName = cleanText(interaction.fields.getTextInputValue('itemName'));
  const price = cleanText(interaction.fields.getTextInputValue('price'));
  const description = cleanText(interaction.fields.getTextInputValue('description'), '');
  const imageUrl = normalizeImageUrl(interaction.fields.getTextInputValue('imageUrl'));
  const expiresAt = new Date(Date.now() + LISTING_DURATION_HOURS * 60 * 60 * 1000);

  const listing = createListingRecord({
    type,
    sellerId: interaction.user.id,
    sellerName: displayName(interaction.user),
    itemName,
    category,
    price,
    description,
    imageUrl,
    guildId: interaction.guildId,
    expiresAt: expiresAt.toISOString(),
  });

  const channel = await interaction.client.channels.fetch(env.MARKET_CHANNEL_ID);
  if (!channel || !channel.isTextBased()) {
    throw new Error('Canal do mercado invalido ou inacessivel.');
  }

  const message = await channel.send({
    embeds: [listingEmbed({ ...listing, expiresAt })],
    components: [listingButtons(listing.id, false, listing.type)],
  });

  updateListing(listing.id, (current) => ({
    ...current,
    channelId: message.channelId,
    messageId: message.id,
  }));

  await interaction.reply({
    embeds: [createdEmbed(listing)],
    components: [createdListingButtons(listing.id)],
    ephemeral: true,
  });
}

async function requestListingImage(interaction, listingId) {
  const listing = findListingById(listingId);
  if (!listing || listing.status !== 'active') {
    await interaction.reply({ content: 'Este anuncio nao esta mais ativo.', ephemeral: true });
    return;
  }

  if (listing.sellerId !== interaction.user.id) {
    await interaction.reply({ content: 'Apenas o dono do anuncio pode adicionar imagem.', ephemeral: true });
    return;
  }

  startImageUpload({
    userId: interaction.user.id,
    guildId: interaction.guildId,
    channelId: interaction.channelId,
    listingId: listing.id,
  });

  await interaction.reply({
    content: 'Cole o print do item neste canal com Ctrl+V em ate 2 minutos.',
    ephemeral: true,
  });
}

async function sendInterest(interaction, listingId) {
  const listing = findListingById(listingId);
  if (!listing || listing.status !== 'active') {
    await interaction.reply({ content: 'Este anuncio nao esta mais ativo.', ephemeral: true });
    return;
  }

  if (listing.sellerId === interaction.user.id) {
    await interaction.reply({ content: 'Voce nao pode demonstrar interesse no proprio anuncio.', ephemeral: true });
    return;
  }

  const existing = findOpenConversation(listing.id, interaction.user.id);
  if (existing) {
    const channel = await interaction.client.channels.fetch(existing.channelId).catch(() => null);
    if (channel) {
      await interaction.reply({
        content: `Voce ja tem uma conversa aberta para este anuncio: ${channel}`,
        ephemeral: true,
      });
      return;
    }
  }

  const conversationChannel = await createNegotiationChannel(interaction, listing);
  if (!conversationChannel) return;

  try {
    const seller = await interaction.client.users.fetch(listing.sellerId);
    await seller.send({
      embeds: [dmInterestEmbed(listing, interaction.user)],
      content: `Conversa aberta: ${conversationChannel}`,
    });
  } catch {}

  await interaction.reply({
    content: `Conversa criada com o vendedor: ${conversationChannel}`,
    ephemeral: true,
  });
}

async function createNegotiationChannel(interaction, listing) {
  const marketChannel = await interaction.client.channels.fetch(env.MARKET_CHANNEL_ID).catch(() => null);
  const parentId = env.NEGOTIATION_CATEGORY_ID || marketChannel?.parentId || null;
  const channelName = buildNegotiationChannelName(listing.itemName, interaction.user.username);

  try {
    const channel = await interaction.guild.channels.create({
      name: channelName,
      type: ChannelType.GuildText,
      parent: parentId,
      topic: `Mercado Drakoria | ${listing.itemName} | Vendedor ${listing.sellerId} | Cliente ${interaction.user.id}`,
      permissionOverwrites: [
        {
          id: interaction.guild.roles.everyone.id,
          deny: [PermissionFlagsBits.ViewChannel],
        },
        {
          id: listing.sellerId,
          allow: [
            PermissionFlagsBits.ViewChannel,
            PermissionFlagsBits.SendMessages,
            PermissionFlagsBits.ReadMessageHistory,
            PermissionFlagsBits.AttachFiles,
            PermissionFlagsBits.EmbedLinks,
          ],
        },
        {
          id: interaction.user.id,
          allow: [
            PermissionFlagsBits.ViewChannel,
            PermissionFlagsBits.SendMessages,
            PermissionFlagsBits.ReadMessageHistory,
            PermissionFlagsBits.AttachFiles,
            PermissionFlagsBits.EmbedLinks,
          ],
        },
        {
          id: interaction.client.user.id,
          allow: [
            PermissionFlagsBits.ViewChannel,
            PermissionFlagsBits.SendMessages,
            PermissionFlagsBits.ManageChannels,
            PermissionFlagsBits.ReadMessageHistory,
            PermissionFlagsBits.EmbedLinks,
          ],
        },
      ],
    });

    const conversation = createConversation({
      listingId: listing.id,
      guildId: interaction.guildId,
      channelId: channel.id,
      sellerId: listing.sellerId,
      buyerId: interaction.user.id,
    });

    await channel.send({
      content: `<@${listing.sellerId}> ${interaction.user}`,
      embeds: [negotiationEmbed(listing, interaction.user)],
      components: [negotiationButtons(conversation.id)],
    });

    return channel;
  } catch (error) {
    console.error('[Mercado Drakoria] Falha ao criar conversa privada:', error);
    await interaction.reply({
      content: 'Nao consegui criar a conversa privada. Verifique se o bot tem permissao de Gerenciar Canais.',
      ephemeral: true,
    });
    return null;
  }
}

async function closeConversation(interaction, conversationId) {
  const conversation = findConversationById(conversationId);
  if (!conversation || conversation.status !== 'open') {
    await interaction.reply({ content: 'Esta conversa ja foi encerrada.', ephemeral: true });
    return;
  }

  const allowed = [conversation.sellerId, conversation.buyerId].includes(interaction.user.id);
  if (!allowed) {
    await interaction.reply({ content: 'Apenas vendedor ou cliente podem encerrar esta conversa.', ephemeral: true });
    return;
  }

  closeConversationRecord(conversation.id);
  await interaction.reply({ content: 'Conversa encerrada. Este canal sera removido em alguns segundos.', ephemeral: true });

  setTimeout(async () => {
    const channel = await interaction.client.channels.fetch(conversation.channelId).catch(() => null);
    if (channel) {
      await channel.delete('Conversa do Mercado Drakoria encerrada.').catch(() => null);
    }
  }, 5000);
}

function buildNegotiationChannelName(itemName, buyerName) {
  const raw = `negociacao-${itemName}-${buyerName}`;
  return raw
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 90) || 'negociacao-mercado';
}

function normalizeImageUrl(value) {
  const text = String(value || '').trim();
  if (!text) return '';

  try {
    const url = new URL(text);
    if (!['http:', 'https:'].includes(url.protocol)) return '';
    if (!/\.(png|jpe?g|gif|webp)(\?.*)?$/i.test(url.toString())) return '';
    return url.toString();
  } catch {
    return '';
  }
}

async function closeListing(interaction, listingId) {
  const listing = findListingById(listingId);
  if (!listing || listing.status !== 'active') {
    await interaction.reply({ content: 'Este anuncio ja foi encerrado.', ephemeral: true });
    return;
  }

  if (listing.sellerId !== interaction.user.id) {
    await interaction.reply({ content: 'Apenas o dono pode encerrar este anuncio.', ephemeral: true });
    return;
  }

  const closedListing = updateListing(listing.id, (current) => ({
    ...current,
    status: 'closed',
  }));

  await editListingAsClosed(interaction.client, closedListing);
  await interaction.reply({ content: 'Anuncio encerrado.', ephemeral: true });
}

async function showMyListings(interaction) {
  const listings = findActiveListingsBySeller(interaction.guildId, interaction.user.id, 5);

  await interaction.reply({
    embeds: [myListingsEmbed(listings)],
    components: myListingCloseButtons(listings),
    ephemeral: true,
  });
}

async function editListingAsClosed(client, listing) {
  if (!listing || !listing.channelId || !listing.messageId) return;

  try {
    const channel = await client.channels.fetch(listing.channelId);
    if (!channel || !channel.isTextBased()) return;

    const message = await channel.messages.fetch(listing.messageId);
    await message.edit({
      embeds: [listingEmbed(listing, { closed: true })],
      components: [listingButtons(listing.id, true, listing.type)],
    });
  } catch (error) {
    console.warn(`[Mercado Drakoria] Nao foi possivel editar anuncio ${listing.id}:`, error.message);
  }
}

module.exports = {
  createListing,
  sendInterest,
  closeListing,
  showMyListings,
  editListingAsClosed,
  closeConversation,
  requestListingImage,
};
