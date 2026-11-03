# TinyD

TinyD is a deterministic, event-sourced execution platform for AI orchestration and distributed systems.

## Overview

TinyD provides deterministic workflow execution, replayable state transitions, event sourcing, capability-based execution, auditability, and multi-tenant orchestration. It serves as the execution runtime for the Nexus AI platform.

## Core Features
- Deterministic execution
- Event sourcing
- Replay and verification
- Versioned specifications
- Kafka-native messaging
- Multi-tenant architecture
- Observable execution
- Local-first searchable archive engine

## Repository Structure
- `apps/` – applications
- `packages/` – shared libraries
- `docs/` – documentation
- `archive-engine/` – ingestion, normalization, SQLite FTS5 indexing, and search for project archives
- `.github/` – CI/CD and repository automation

## Searchable Archive

`archive-engine/` provides a deterministic foundation for building a searchable archive from exported conversations and project files. It preserves source material, generates content-addressed archive IDs, supports idempotent ingestion, and indexes normalized objects with SQLite FTS5.

Example:

```bash
python -m archive_engine.cli init --db data/index/archive.db
python -m archive_engine.cli ingest ./data/raw --db data/index/archive.db
python -m archive_engine.cli search "TinyD replay" --db data/index/archive.db
```

The archive is populated only from files that are actually supplied to the ingestion pipeline; the repository does not imply that it contains a user's complete personal history.

## Getting Started
Clone the repository, install project dependencies, configure required environment variables, and start the platform using the project-specific build scripts.

## License
Licensed under the Apache License 2.0. See `LICENSE` for the complete license text.

## Attribution
Copyright © 2026 NoShower1Life-Built.

TinyD is the execution runtime foundation of the Nexus AI platform.

## Contributing
Contributions should preserve deterministic execution, replayability, and backward compatibility where applicable.