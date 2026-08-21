from .database import connect


def search(path: str, query: str, limit: int = 50) -> list[dict]:
    with connect(path) as db:
        rows = db.execute(
            "SELECT o.id,o.type,o.title,o.project,o.source,substr(o.content,1,500) FROM search_index s JOIN objects o ON o.id=s.id WHERE search_index MATCH ? LIMIT ?",
            (query, limit),
        ).fetchall()
    return [
        {"id": r[0], "type": r[1], "title": r[2], "project": r[3], "source": r[4], "preview": r[5]}
        for r in rows
    ]
