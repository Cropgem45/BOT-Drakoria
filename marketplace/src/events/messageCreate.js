const { handleImageMessage } = require('../services/imageUploadService');

module.exports = {
  name: 'messageCreate',
  async execute(message) {
    try {
      await handleImageMessage(message);
    } catch (error) {
      console.error('[Mercado Drakoria] Falha ao processar imagem do anuncio:', error);
    }
  },
};
