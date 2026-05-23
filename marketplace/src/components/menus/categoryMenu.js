const { ActionRowBuilder, StringSelectMenuBuilder } = require('discord.js');
const { categories } = require('../../config/constants');
const { ids } = require('../../utils/componentIds');

function categoryMenu(type = 'sell') {
  return new ActionRowBuilder().addComponents(
    new StringSelectMenuBuilder()
      .setCustomId(ids.categorySelect(type))
      .setPlaceholder('Escolha a categoria do item')
      .addOptions(
        Object.entries(categories).map(([value, category]) => ({
          label: category.label,
          value,
          emoji: category.emoji,
        })),
      ),
  );
}

module.exports = { categoryMenu };
