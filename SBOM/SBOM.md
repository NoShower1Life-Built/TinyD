# TinyD Software Bill of Materials

Generated: 2026-08-20
Repository: NoShower1Life-Built/TinyD
Commit audited: 458c0494738b4c0c6257413e71783de43bb180c3

## Inventory result

The repository declares one application package:

- TinyD
- Version: 1.0.0-alpha
- Python requirement: >=3.11
- Description: Deterministic event sourced execution runtime

The current `pyproject.toml` contains no third-party runtime dependencies and the repository root does not expose a Python lockfile in the inspected metadata. Therefore the CycloneDX component list is intentionally empty rather than inventing package versions.

## Infrastructure metadata inspected

`docker-compose.yml` defines a local `tinyd-api` service built from the repository and exposed on port 8000. This is deployment configuration, not a separately versioned software dependency, so it is not represented as a third-party component in the SBOM.

## Important limitation

This is a source-declared SBOM, not a resolved-environment SBOM. A complete dependency SBOM requires the exact installed/resolved environment, including transitive dependencies, container base-image digest, OS packages, frontend lockfile contents, and build artifacts. Those items must be generated from the actual build environment before a production release is certified.

## Policy

Do not add guessed versions, licenses, hashes, or package identities. Regenerate this SBOM from the reproducible build environment whenever dependency manifests or container images change.
