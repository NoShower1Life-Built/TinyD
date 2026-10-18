# TinyD Archive Engine

A local-first ingestion, normalization, indexing, and search layer for building a searchable archive from exported conversations, documents, notebooks, and source repositories.

## Design goals

- Preserve source material rather than replacing it with summaries.
- Produce deterministic SHA-256 object identifiers.
- Support SQLite FTS5 for fast local full-text search.
- Keep ingestion idempotent.
- Separate raw input from normalized archive objects.
- Provide a foundation for semantic search and knowledge-graph extraction.

## Layout

- `src/archive_engine/models.py` — canonical archive object model.
- `src/archive_engine/database.py` — SQLite schema and connection management.
- `src/archive_engine/ingest.py` — filesystem and ChatGPT-export ingestion.
- `src/archive_engine/search.py` — FTS5 indexing and querying.
- `src/archive_engine/cli.py` — command-line interface.

## Usage

```bash
python -m archive_engine.cli init --db data/index/archive.db
python -m archive_engine.cli ingest ./data/raw --db data/index/archive.db
python -m archive_engine.cli search "TinyD replay" --db data/index/archive.db
```

The engine does not claim to contain a user's complete history until the corresponding exports/files have actually been supplied and ingested.