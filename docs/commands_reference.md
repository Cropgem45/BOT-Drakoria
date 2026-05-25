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
- `gerar_codigo`: atalho administrativo dentro do grupo beta; tambem existe como comando de topo `/gerar_codigo`. Todo codigo gerado vale 1 uso.
- `ativar_influencer`: reativa um codigo de influencer.
- `desativar_influencer`: desativa um codigo de influencer.
- `resetar_vagas`: zera as vagas usadas de um codigo ou de todos os influencers.
- `listar_influencers`: lista os codigos de influencer cadastrados e vagas usadas.
- `stats_influencer`: mostra estatisticas de candidaturas por codigo.
- Painel de vagas: o bot mantém a sala `vagas-beta` (`1508552344923799803`) atualizada com usadas/pendentes/restantes por influencer.

## /gerar_codigo

- Exclusivo do cargo Criador de Conteudo (`1487647366327570574`); gera codigo individual e unico de influencer para ingresso beta. Cada codigo vale 1 pessoa, 1 unica vez. O limite de 5 vagas e por influencer marcado/dono do codigo.

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
