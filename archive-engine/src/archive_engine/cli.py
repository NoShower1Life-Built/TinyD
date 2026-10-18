import argparse

from .database import initialize
from .ingest import ingest_path
from .search import search


def main() -> None:
    parser = argparse.ArgumentParser(prog="tinyd-archive")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--db", default="data/index/archive.db")

    ingest = sub.add_parser("ingest")
    ingest.add_argument("path")
    ingest.add_argument("--db", default="data/index/archive.db")

    query = sub.add_parser("search")
    query.add_argument("query")
    query.add_argument("--db", default="data/index/archive.db")
    query.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()
    if args.command == "init":
        initialize(args.db)
        print(f"initialized {args.db}")
    elif args.command == "ingest":
        initialize(args.db)
        print(f"ingested {ingest_path(args.path, args.db)} objects")
    elif args.command == "search":
        for result in search(args.db, args.query, args.limit):
            print(f"[{result['type']}] {result['title']} — {result['project']}\n{result['preview']}\n")


if __name__ == "__main__":
    main()
