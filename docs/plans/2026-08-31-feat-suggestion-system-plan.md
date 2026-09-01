---
title: "feat: restaurar sistema de sugestões"
type: plan
date: 2026-08-31
status: approved
confidence: high
---

# Restaurar sistema de sugestões

## Problema

O comando `/sugestao` existia no bot antigo, mas não está presente na versão atual. O servidor precisa novamente de um fluxo simples para coletar sugestões, abrir discussão e contabilizar votos.

## Solução

Adicionar uma cog de sugestões integrada ao SQLite já usado pelo bot. O comando abre um modal, publica um embed no canal configurado, cria uma thread automaticamente e adiciona botões persistentes de voto. Cada membro terá um único voto ativo por sugestão, podendo trocar de opção.

## Tarefas

- [ ] Adicionar configuração e acesso ao canal de sugestões.
- [ ] Criar tabelas e métodos para sugestões e votos.
- [ ] Implementar `/sugestao`, modal, embed, thread e views persistentes.
- [ ] Adicionar testes para criação, voto único e troca de voto.
- [ ] Validar, revisar diff, commitar e publicar conforme o workflow.

## Critérios de aceitação

- `/sugestao` aparece na guild oficial e abre o formulário.
- Uma sugestão gera uma mensagem embed e uma thread vinculada automaticamente.
- Um membro não acumula votos em Sim e Não.
- Trocar o voto atualiza os totais no embed.
- Os botões continuam funcionando após reiniciar o bot.

## Decisões e riscos

- O banco atual será reutilizado para evitar perda de dados e dependências novas.
- O canal será configurável, com o ID atual como valor de referência.
- A criação da thread depende das permissões `CreatePublicThreads` e `SendMessagesInThreads`; falha nessa etapa deverá ser registrada sem apagar a sugestão.
