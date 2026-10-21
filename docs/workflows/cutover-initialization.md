# Cutover development rehearsal and future launch

ADR-027 governs. This is not a reset feature and is never run automatically at startup.

## Development rehearsal (completed October 20, 2026)

`tools/archive_cutover_development.py --new-database rhp_cutover_dev_<suffix>` previews the operation;
`--apply` archives RHP's database/media, restores into a fresh scratch database, compares table counts,
and creates a separate empty database. It never drops databases or edits environment files. It refuses
production settings. The archive contains private data: keep its directory restricted and out of Git.

Before switching the local web service, apply migrations to the new database and verify its identity.
Retain only active administrator logins for access, with no tenant, portfolio or financial copy. Use
clearly synthetic examples. Set a separate media directory and restart only the RHP web service.
The original database, private media, verified restore and archive remain available.

Current archive: `.uv-cache/cutover-backups/20261020T235016Z_35246782/manifest.json`.
It is local only: arrange protected off-host backups before live operation.

## Recovery without rewriting the original

Verify the manifest's dump/media checksums. Restore into a NEW explicitly named database, and extract
files into a NEW private directory. Apply additive migrations to that restored copy before running
current code. Verify counts, private downloads and ledger totals; point development at that copy only
after verification. Do not run current code against an older schema, delete the original, reset Git,
overwrite the archive, or alter ecosystem databases. Keep uncommitted implementation work intact.

## Future production initialization — separate confirmation required

1. Obtain explicit owner confirmation of the target database, media directory, launch date and downtime.
2. Back up any existing target data/files and verify restoration; do not reuse the development-reset tool.
3. Provision a new production database and private media destination; run migrations and deployment checks.
4. Establish authorized staff access without demo credentials or synthetic tenant/property records.
5. Enter Robert's actual properties, units, people and true lease terms. Review the actual RHP start date.
6. Review and confirm each stated debt, credit or zero with notes and optional evidence. Mark unavailable
   history honestly; do not infer prior payments or deposits held from lease terms.
7. Verify tenant isolation, actual balances, private downloads and post-cutover charging before access.
8. Accounting remains unavailable until its separately reviewed openings and reconciliation are approved.

There is no delete-all command, scheduled clearing or product reset button. Rehearsal approval is not
permission to clear future production records.
