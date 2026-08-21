from dataclasses import asdict, dataclass, field
import hashlib
import json


@dataclass(frozen=True)
class ArchiveObject:
    type: str
    title: str
    content: str
    source: str
    project: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def id(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def record(self) -> dict:
        value = asdict(self)
        value["id"] = self.id
        value["tags"] = list(self.tags)
        return value
