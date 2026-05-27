const {
  ChannelType,
  OverwriteType,
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
const { deferEphemeral, sendEphemeral } = require('../utils/respond');

async function createListing(interaction, category, type = 'sell') {
  await deferEphemeral(interaction);

  if (!env.MARKET_CHANNEL_ID) {
    await sendEphemeral(interaction, {
      content: 'O canal do mercado ainda nao foi configurado em MARKET_CHANNEL_ID.',
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

  await sendEphemeral(interaction, {
    embeds: [createdEmbed(listing)],
    components: [createdListingButtons(listing.id)],
  });
}

async function requestListingImage(interaction, listingId) {
  await deferEphemeral(interaction);

  const listing = findListingById(listingId);
  if (!listing || listing.status !== 'active') {
    await sendEphemeral(interaction, { content: 'Este anuncio nao esta mais ativo.' });
    return;
  }

  if (listing.sellerId !== interaction.user.id) {
    await sendEphemeral(interaction, { content: 'Apenas o dono do anuncio pode adicionar imagem.' });
    return;
  }

  startImageUpload({
    userId: interaction.user.id,
    guildId: interaction.guildId,
    channelId: interaction.channelId,
    listingId: listing.id,
  });

  await sendEphemeral(interaction, {
    content: 'Cole o print do item neste canal com Ctrl+V em ate 2 minutos.',
  });
}

async function sendInterest(interaction, listingId) {
  await deferEphemeral(interaction);

  const listing = findListingById(listingId);
  if (!listing || listing.status !== 'active') {
    await sendEphemeral(interaction, { content: 'Este anuncio nao esta mais ativo.' });
    return;
  }

  if (listing.sellerId === interaction.user.id) {
    await sendEphemeral(interaction, { content: 'Voce nao pode demonstrar interesse no proprio anuncio.' });
    return;
  }

  const existing = findOpenConversation(listing.id, interaction.user.id);
  if (existing) {
    const channel = await interaction.client.channels.fetch(existing.channelId).catch(() => null);
    if (channel) {
      await sendEphemeral(interaction, {
        content: `Voce ja tem uma conversa aberta para este anuncio: ${channel}`,
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

  await sendEphemeral(interaction, {
    content: `Conversa criada com o vendedor: ${conversationChannel}`,
  });
}

async function createNegotiationChannel(interaction, listing) {
  const marketChannel = await interaction.client.channels.fetch(env.MARKET_CHANNEL_ID).catch(() => null);
  const parentId = env.NEGOTIATION_CATEGORY_ID || marketChannel?.parentId || null;
  const channelName = buildNegotiationChannelName(listing.itemName, interaction.user.username);

  try {
    const botMember = await interaction.guild.members.fetchMe();
    const missingGuildPerms = [];
    if (!botMember.permissions.has(PermissionFlagsBits.ManageChannels)) missingGuildPerms.push('Gerenciar Canais');
    if (!botMember.permissions.has(PermissionFlagsBits.ViewChannel)) missingGuildPerms.push('Ver Canais');
    if (missingGuildPerms.length) {
      await sendEphemeral(interaction, {
        content: `Nao consegui criar a conversa privada. Permissoes faltando no bot: ${missingGuildPerms.join(', ')}.`,
      });
      return null;
    }

    if (parentId) {
      const parent = await interaction.guild.channels.fetch(parentId).catch(() => null);
      if (parent) {
        const parentPerms = parent.permissionsFor(botMember);
        const missingParentPerms = [];
        if (!parentPerms?.has(PermissionFlagsBits.ViewChannel)) missingParentPerms.push('Ver Canal (na categoria)');
        if (!parentPerms?.has(PermissionFlagsBits.ManageChannels)) missingParentPerms.push('Gerenciar Canais (na categoria)');
        if (missingParentPerms.length) {
          await sendEphemeral(interaction, {
            content: `Nao consegui criar a conversa privada na categoria atual. Permissoes faltando: ${missingParentPerms.join(', ')}.`,
          });
          return null;
        }
      }
    }

    const channel = await interaction.guild.channels.create({
      name: channelName,
      type: ChannelType.GuildText,
      parent: parentId,
      topic: `Mercado Drakoria | ${listing.itemName} | Vendedor ${listing.sellerId} | Cliente ${interaction.user.id}`,
      permissionOverwrites: [
        {
          id: interaction.guild.roles.everyone.id,
          type: OverwriteType.Role,
          deny: [PermissionFlagsBits.ViewChannel],
        },
        {
          id: listing.sellerId,
          type: OverwriteType.Member,
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
          type: OverwriteType.Member,
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
          type: OverwriteType.Member,
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
    console.error('[Mercado Drakoria] Falha ao criar conversa privada:', {
      message: error?.message,
      code: error?.code,
      status: error?.status,
      rawError: error?.rawError,
    });
    await sendEphemeral(interaction, {
      content: 'Nao consegui criar a conversa privada. Verifique se o bot tem permissao de Gerenciar Canais e acesso a categoria.',
    });
    return null;
  }
}

async function closeConversation(interaction, conversationId) {
  await deferEphemeral(interaction);

  const conversation = findConversationById(conversationId);
  if (!conversation || conversation.status !== 'open') {
    await sendEphemeral(interaction, { content: 'Esta conversa ja foi encerrada.' });
    return;
  }

  const allowed = [conversation.sellerId, conversation.buyerId].includes(interaction.user.id);
  if (!allowed) {
    await sendEphemeral(interaction, { content: 'Apenas vendedor ou cliente podem encerrar esta conversa.' });
    return;
  }

  closeConversationRecord(conversation.id);
  await sendEphemeral(interaction, { content: 'Conversa encerrada. Este canal sera removido em alguns segundos.' });

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
  await deferEphemeral(interaction);

  const listing = findListingById(listingId);
  if (!listing || listing.status !== 'active') {
    await sendEphemeral(interaction, { content: 'Este anuncio ja foi encerrado.' });
    return;
  }

  if (listing.sellerId !== interaction.user.id) {
    await sendEphemeral(interaction, { content: 'Apenas o dono pode encerrar este anuncio.' });
    return;
  }

  const closedListing = updateListing(listing.id, (current) => ({
    ...current,
    status: 'closed',
    closedAt: new Date().toISOString(),
  }));

  await editListingAsClosed(interaction.client, closedListing);
  await sendEphemeral(interaction, { content: 'Anuncio encerrado.' });
}

async function showMyListings(interaction) {
  await deferEphemeral(interaction);

  const listings = findActiveListingsBySeller(interaction.guildId, interaction.user.id, 5);

  await sendEphemeral(interaction, {
    embeds: [myListingsEmbed(listings)],
    components: myListingCloseButtons(listings),
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

async function editListingAsActive(client, listing) {
  if (!listing || !listing.channelId || !listing.messageId) return;

  try {
    const channel = await client.channels.fetch(listing.channelId);
    if (!channel || !channel.isTextBased()) return;

    const message = await channel.messages.fetch(listing.messageId);
    await message.edit({
      embeds: [listingEmbed(listing)],
      components: [listingButtons(listing.id, false, listing.type)],
    });
  } catch (error) {
    console.warn(`[Mercado Drakoria] Nao foi possivel atualizar timer do anuncio ${listing.id}:`, error.message);
  }
}

module.exports = {
  createListing,
  sendInterest,
  closeListing,
  showMyListings,
  editListingAsClosed,
  editListingAsActive,
  closeConversation,
  requestListingImage,
};
