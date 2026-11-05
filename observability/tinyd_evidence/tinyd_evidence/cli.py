from __future__ import annotations

import argparse
from pathlib import Path

from .collector import export_bundle, read_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description="Export observed TinyD runtime records for one trace.")
    parser.add_argument("--events", nargs="+", required=True, type=Path, help="JSONL runtime log file(s)")
    parser.add_argument("--trace-id", required=True, help="Exact trace ID to export")
    parser.add_argument("--out", required=True, type=Path, help="Output evidence directory")
    parser.add_argument("--zip", action="store_true", help="Also create a ZIP archive")
    args = parser.parse_args()

    records = read_jsonl(args.events)
    manifest = export_bundle(records, args.trace_id, args.out, args.zip)
    print(f"trace_id={args.trace_id}")
    print(f"assessment={manifest['completeness']['assessment']}")
    print(f"record_count={manifest['completeness']['record_count']}")
    print(f"output={args.out}")
    if args.zip:
        print(f"archive={args.out.with_suffix('.zip')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
