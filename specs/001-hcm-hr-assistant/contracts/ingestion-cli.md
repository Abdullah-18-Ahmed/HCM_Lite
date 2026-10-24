# Contract: Ingestion CLI

Entry point: `python -m hcm_lite.rag.ingest [command] [options]`

| Command | Behaviour | Exit code |
|---------|-----------|-----------|
| `ingest` (default) | Incremental: load new, update changed, skip unchanged, delete removed documents from `DOCUMENTS_DIR` | 0 = success; 2 = at least one document rejected (others loaded); 1 = fatal (config / vector store unreachable) |
| `rebuild` | Drop and recreate the collection, then a full ingest | same as above |
| `status` | Print collection name, point count, embedding model, and last report summary | 0 / 1 |
| `clear --yes` | Delete the development collection and registry. Refuses without `--yes`, and refuses when `VECTOR_STORE_URL` is set unless `--allow-remote` is also given | 0 / 1 |

Options: `--source PATH` (overrides `DOCUMENTS_DIR`), `--json` (report as JSON on stdout).

## Output (human-readable)

```text
HCM Lite ingestion — DEMO MODE
  loaded     policies/annual-leave.md            6 chunks
  unchanged  policies/remote-work.md
  rejected   policies/broken.pdf                 reason: PDF has no extractable text
Totals: loaded=1 updated=0 unchanged=1 rejected=1 deleted=0 chunks_written=6
Report: .ingest/last_report.json
```

## Guarantees

- Idempotent: running `ingest` twice on unchanged files writes 0 chunks the second time.
- Supported extensions: `.md`, `.txt`, `.pdf`. Anything else is `rejected: unsupported format`.
- Files over 10 MB, empty after cleaning, or unreadable are rejected with a reason.
- The registry (`.ingest/registry.json`: document_id → content_hash, version, chunk count) is the
  source of truth for change detection; it is rebuilt from the collection when missing.
- No document text and no secrets are written to logs; the report contains paths and statuses only.
