from pathlib import Path
import json

from .models import ArchiveObject
from .database import upsert


def _chatgpt_objects(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    conversations = data if isinstance(data, list) else data.get("conversations", [])
    for conversation in conversations:
        title = conversation.get("title", "Untitled conversation")
        parts = []
        mapping = conversation.get("mapping", {})
        for node in mapping.values():
            message = node.get("message") if isinstance(node, dict) else None
            if not message:
                continue
            content = message.get("content", {})
            parts.extend(str(part) for part in content.get("parts", []) if isinstance(part, (str, int, float)))
        yield ArchiveObject("conversation", title, "\n".join(parts), str(path))


def ingest_path(root: str | Path, db_path: str | Path) -> int:
    root = Path(root)
    count = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            if path.suffix.lower() == ".json" and "conversation" in path.name.lower():
                objects = _chatgpt_objects(path)
            elif path.suffix.lower() in {".md", ".txt", ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yaml", ".yml"}:
                text = path.read_text(encoding="utf-8", errors="replace")
                objects = [ArchiveObject("source", path.name, text, str(path))]
            else:
                continue
            for obj in objects:
                upsert(db_path, obj.record())
                count += 1
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
    return count
