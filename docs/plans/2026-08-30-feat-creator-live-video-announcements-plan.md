---
title: "feat: divulgação automática de lives e vídeos de criadores"
type: plan
date: 2026-08-30
status: approved
confidence: medium
---

# Divulgação automática de criadores

## Resumo

Adicionar ao bot um monitor simples e assíncrono para Twitch e YouTube. O monitor publica no canal Discord configurado somente conteúdos relacionados a `Drakoria`, evitando duplicatas e mantendo anúncios históricos.

## Solução proposta

- Criadores fixos em `config/example_config.json`, com os identificadores reais mantidos em configuração privada da VPS.
- Twitch: consultar os canais cadastrados e anunciar streams ativas cujo título contenha `Drakoria`, ignorando maiúsculas/minúsculas.
- YouTube: consultar vídeos recentes de cada canal, ler título e descrição e anunciar apenas os que contenham `Drakoria`.
- Persistir IDs já anunciados no SQLite existente para sobreviver a reinícios.
- Usar uma tarefa periódica assíncrona, com timeout, logs e tolerância a falhas de uma plataforma.
- Enviar embed com `@everyone`; a identidade visual especial do embaixador Diogo será refinada depois da validação do fluxo básico.

## Tarefas de implementação

- [ ] Adicionar configuração de anúncios, canal de destino, palavra-chave, intervalo e criadores.
- [ ] Adicionar armazenamento SQLite de conteúdos anunciados.
- [ ] Criar clientes mínimos para Twitch e YouTube usando HTTP assíncrono.
- [ ] Criar serviço de monitoramento e embed de anúncio.
- [ ] Integrar o serviço ao ciclo de vida do bot sem bloquear o Gateway.
- [ ] Adicionar testes para normalização, filtro, deduplicação e construção dos embeds.
- [ ] Atualizar documentação e `.env.example`/runbook sem incluir segredos.
- [ ] Validar, revisar diff, commitar somente os arquivos da funcionalidade e fazer deploy conforme o fluxo existente.

## Critérios de aceitação

- Um título Twitch com qualquer variação de `Drakoria` gera um anúncio apenas enquanto a stream está ativa.
- Um vídeo YouTube só gera anúncio quando título ou descrição contém a palavra, sem diferenciar maiúsculas/minúsculas.
- Reiniciar o bot não duplica conteúdo já anunciado.
- Falha ou timeout em uma API não derruba o bot nem impede comandos Discord.
- O anúncio chega no canal `1508132406199324692` com link, título, criador e `@everyone`.
- Lives encerradas e vídeos já anunciados permanecem no Discord.

## Decisões e riscos

- Polling foi escolhido por simplicidade e menor superfície operacional; webhooks ficam para uma fase posterior.
- Segredos ficam em arquivo privado ignorado pelo Git; nunca serão colocados em configuração versionada.
- A API do YouTube exige uma chave de API; a Twitch exige Client ID e Client Secret para obter token de aplicação.
- O intervalo e o volume de consultas serão conservadores para respeitar quotas e rate limits.

## Referências

- https://dev.twitch.tv/docs/api/reference
- https://developers.google.com/youtube/v3/docs/search/list
- https://developers.google.com/youtube/v3/docs/videos/list
