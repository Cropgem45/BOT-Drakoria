# Commands Reference

Referencia dos comandos ativos no fechamento.

## /admin

- `healthcheck`: auditoria operacional completa.
- `server_map`: mapa de IDs configurados e recursos resolvidos.

## /cadastro

- `status`: status cadastral de um membro.
- `publicar_painel`: publica/sincroniza o painel de cadastro oficial.

## /beta_program

- `publicar_painel`: publica/sincroniza painel fechado do programa beta.
- `cadastrar_influencer`: cria ou atualiza codigo de influencer para ingresso beta, com 5 vagas por padrao.
- `ativar_influencer`: reativa um codigo de influencer.
- `desativar_influencer`: desativa um codigo de influencer.
- `listar_influencers`: lista os codigos de influencer cadastrados e vagas usadas.
- `stats_influencer`: mostra estatisticas de candidaturas por codigo.

## /ticket

- `painel`: publica/sincroniza painel de tickets.
- `abrir`: abre ticket manual por tipo.
- `fechar`: encerra ticket atual com motivo.

## /anuncio

- `anuncio`: abre modal para publicacao de anuncio oficial.

## /adddonate

- `usuario valor`: adiciona uma doacao ao Trono dos Patronos.

## /removedonate

- `usuario valor`: remove valor por correcao administrativa sem permitir total negativo.

## /setdonate

- `usuario valor`: define o total exato de um patrono.

## /top

- `refresh`: sincroniza manualmente a embed fixa do ranking.
- `reset`: reseta o ranking com confirmacao `CONFIRMAR`.

## /pontos

- `estado`: estado do expediente de um membro.
- `encerrar`: encerra expediente manualmente.
- `listar`: lista sessoes ativas.
- `tolerancias`: lista sessoes em tolerancia.
- `diagnosticar`: diagnostico por membro.
- `limpar`: limpeza de sessao stale com seguranca.
- `staff`: relatorio individual premium.
- `gestao`: publica/sincroniza dashboard executivo.
- `resumo`: resumo executivo por periodo (semanal/mensal).
