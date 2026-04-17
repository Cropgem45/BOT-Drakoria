# Final Production Checklist

Status values:
- `OK`: pronto para producao
- `ALERTA`: funciona, mas exige monitoramento
- `FALTA AJUSTE`: bloquear deploy ate corrigir

## Homologacao Final

- [ ] Configuracao valida no boot (`/admin healthcheck`)
- [ ] IDs de canais/cargos resolvidos (`/admin server_map`)
- [ ] Painel `Registrar-se` sincronizado
- [ ] Painel `Cadastro Oficial` sincronizado
- [ ] Painel `Programa Beta` sincronizado
- [ ] Painel `Tickets` sincronizado
- [ ] Voice Points ativo e reconciliacao sem stale
- [ ] Dashboard de gestao publicado
- [ ] Logs operacionais chegando nos canais corretos
- [ ] Fluxos com DM falhando sem quebrar operacao principal
- [ ] Restart do bot mantendo views persistentes

## Seguranca e Permissoes

- [ ] Permissoes centralizadas via `PermissionService`
- [ ] Comandos sensiveis protegidos por roles/administrador
- [ ] Sem regra de negocio baseada em nome visual
- [ ] Regras principais por ID (canais, roles, guild)

## Persistencia

- [ ] SQLite integra (`PRAGMA integrity_check = ok`)
- [ ] Tabelas obrigatorias presentes
- [ ] Sem duplicidade indevida de sessao/cadastro/candidatura

## Operacao

- [ ] Comandos principais documentados
- [ ] Troubleshooting basico documentado
- [ ] Procedimento de reset/backups definido
