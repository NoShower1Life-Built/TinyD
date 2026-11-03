from pathlib import Path
import sqlite3


def connect(path: str | Path) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def initialize(path: str | Path) -> None:
    with connect(path) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS objects (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                project TEXT NOT NULL,
                source TEXT NOT NULL,
                content TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT ''
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS search_index
            USING fts5(id UNINDEXED, title, project, source, content, tags);
            """
        )


def upsert(path: str | Path, record: dict) -> None:
    with connect(path) as db:
        db.execute(
            "INSERT OR REPLACE INTO objects(id,type,title,project,source,content,tags) VALUES(?,?,?,?,?,?,?)",
            (record["id"], record["type"], record["title"], record["project"], record["source"], record["content"], ",".join(record["tags"])),
        )
        db.execute("DELETE FROM search_index WHERE id = ?", (record["id"],))
        db.execute(
            "INSERT INTO search_index(id,title,project,source,content,tags) VALUES(?,?,?,?,?,?)",
            (record["id"], record["title"], record["project"], record["source"], record["content"], ",".join(record["tags"])),
        )
