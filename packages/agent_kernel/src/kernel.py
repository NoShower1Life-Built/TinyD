from __future__ import annotations

import hashlib
import json
import random
import sqlite3
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


class KernelError(RuntimeError):
    pass


class ToolBlocked(KernelError):
    pass


@dataclass(frozen=True)
class Tool:
    name: str
    handler: Callable[[dict[str, Any]], Any]
    description: str = ""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, name: str, handler: Callable[[dict[str, Any]], Any], description: str = "") -> None:
        if not name or not name.replace("_", "").replace("-", "").isalnum():
            raise ValueError("tool name must be a non-empty identifier")
        if name in self._tools:
            raise ValueError(f"tool already registered: {name}")
        if not callable(handler):
            raise TypeError("handler must be callable")
        self._tools[name] = Tool(name, handler, description)

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KernelError(f"unknown tool: {name}") from exc

    def names(self) -> list[str]:
        return sorted(self._tools)


class KernelStore:
    """Transactional SQLite persistence for artifacts, policy controls, and bandit state.

    Suitable for a single-host runtime. Use the existing TinyD PostgreSQL journal
    and a transactional shared policy store before running multiple worker hosts.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS artifacts (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_id TEXT NOT NULL UNIQUE,
                    tool_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    output_json TEXT,
                    error TEXT,
                    reward REAL,
                    created_at REAL NOT NULL,
                    previous_digest TEXT,
                    digest TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS artifacts_tool_created
                    ON artifacts(tool_name, created_at);
                CREATE TABLE IF NOT EXISTS tool_controls (
                    tool_name TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
                    reason TEXT,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS bandit (
                    tool_name TEXT PRIMARY KEY,
                    alpha REAL NOT NULL CHECK(alpha > 0),
                    beta REAL NOT NULL CHECK(beta > 0),
                    pulls INTEGER NOT NULL DEFAULT 0 CHECK(pulls >= 0),
                    reward_sum REAL NOT NULL DEFAULT 0
                );
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30, isolation_level="DEFERRED")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def is_enabled(self, tool_name: str) -> bool:
        with self._connect() as db:
            row = db.execute("SELECT enabled FROM tool_controls WHERE tool_name=?", (tool_name,)).fetchone()
            return row is None or bool(row["enabled"])

    def set_enabled(self, tool_name: str, enabled: bool, reason: str = "") -> None:
        with self._lock, self._connect() as db:
            db.execute("""
                INSERT INTO tool_controls(tool_name,enabled,reason,updated_at)
                VALUES(?,?,?,?)
                ON CONFLICT(tool_name) DO UPDATE SET
                    enabled=excluded.enabled, reason=excluded.reason, updated_at=excluded.updated_at
            """, (tool_name, int(enabled), reason, time.time()))

    def eligible_tools(self, names: list[str]) -> list[str]:
        return [name for name in names if self.is_enabled(name)]

    def choose_thompson(self, names: list[str], rng: random.Random) -> str:
        if not names:
            raise KernelError("no enabled tools are available")
        with self._connect() as db:
            scores = {}
            for name in names:
                row = db.execute("SELECT alpha,beta FROM bandit WHERE tool_name=?", (name,)).fetchone()
                alpha, beta = (float(row["alpha"]), float(row["beta"])) if row else (1.0, 1.0)
                scores[name] = rng.betavariate(alpha, beta)
        return max(names, key=lambda name: (scores[name], name))

    def record_artifact(
        self, execution_id: str, tool_name: str, status: str, input_json: str,
        output_json: str | None, error: str | None,
    ) -> dict[str, Any]:
        with self._lock, self._connect() as db:
            existing = db.execute("SELECT * FROM artifacts WHERE execution_id=?", (execution_id,)).fetchone()
            if existing:
                return dict(existing)
            head = db.execute("SELECT digest FROM artifacts ORDER BY sequence DESC LIMIT 1").fetchone()
            previous = head["digest"] if head else None
            created = time.time()
            body = {
                "execution_id": execution_id, "tool_name": tool_name, "status": status,
                "input_json": input_json, "output_json": output_json, "error": error,
                "created_at": created, "previous_digest": previous,
            }
            digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            cur = db.execute("""
                INSERT INTO artifacts(execution_id,tool_name,status,input_json,output_json,error,
                                      created_at,previous_digest,digest)
                VALUES(?,?,?,?,?,?,?,?,?)
            """, (execution_id, tool_name, status, input_json, output_json, error, created, previous, digest))
            row = db.execute("SELECT * FROM artifacts WHERE sequence=?", (cur.lastrowid,)).fetchone()
            return dict(row)

    def record_reward(self, execution_id: str, reward: float) -> dict[str, Any]:
        if not 0.0 <= reward <= 1.0:
            raise ValueError("reward must be between 0 and 1")
        with self._lock, self._connect() as db:
            row = db.execute("SELECT tool_name,reward FROM artifacts WHERE execution_id=?", (execution_id,)).fetchone()
            if row is None:
                raise KernelError(f"unknown execution: {execution_id}")
            if row["reward"] is not None:
                raise KernelError("reward already recorded for this execution")
            tool = row["tool_name"]
            db.execute("""
                INSERT INTO bandit(tool_name,alpha,beta,pulls,reward_sum) VALUES(?,?,?,1,?)
                ON CONFLICT(tool_name) DO UPDATE SET
                    alpha=alpha+excluded.alpha-1,
                    beta=beta+excluded.beta-1,
                    pulls=pulls+1,
                    reward_sum=reward_sum+excluded.reward_sum
            """, (tool, 1.0 + reward, 1.0 + (1.0 - reward), reward))
            db.execute("UPDATE artifacts SET reward=? WHERE execution_id=?", (reward, execution_id))
            stats = db.execute("SELECT * FROM bandit WHERE tool_name=?", (tool,)).fetchone()
            return dict(stats)

    def get_artifact(self, execution_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM artifacts WHERE execution_id=?", (execution_id,)).fetchone()
            return dict(row) if row else None

    def list_artifacts(self, limit: int = 100) -> list[dict[str, Any]]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        with self._connect() as db:
            rows = db.execute("SELECT * FROM artifacts ORDER BY sequence DESC LIMIT ?", (limit,)).fetchall()
            return [dict(row) for row in rows]

    def verify_artifact_chain(self) -> bool:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM artifacts ORDER BY sequence ASC").fetchall()
        previous = None
        for row in rows:
            body = {
                "execution_id": row["execution_id"], "tool_name": row["tool_name"],
                "status": row["status"], "input_json": row["input_json"],
                "output_json": row["output_json"], "error": row["error"],
                "created_at": row["created_at"], "previous_digest": previous,
            }
            digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if row["previous_digest"] != previous or row["digest"] != digest:
                return False
            previous = row["digest"]
        return True


class HotBlock:
    """Hard execution gate. Policy changes are explicit; failures never auto-block tools."""

    def __init__(self, store: KernelStore) -> None:
        self.store = store

    def allow(self, tool_name: str) -> None:
        self.store.set_enabled(tool_name, True, "explicitly enabled")

    def block(self, tool_name: str, reason: str) -> None:
        self.store.set_enabled(tool_name, False, reason)

    def check(self, tool_name: str) -> None:
        if not self.store.is_enabled(tool_name):
            raise ToolBlocked(f"tool blocked by HotBlock: {tool_name}")


class BanditPolicy:
    """Thompson-sampling Bernoulli bandit; reward feedback is explicit and bounded [0,1]."""

    def __init__(self, store: KernelStore, seed: int | None = None) -> None:
        self.store = store
        self.rng = random.Random(seed)

    def select(self, tool_names: list[str]) -> str:
        eligible = self.store.eligible_tools(tool_names)
        return self.store.choose_thompson(eligible, self.rng)

    def update(self, execution_id: str, reward: float) -> dict[str, Any]:
        return self.store.record_reward(execution_id, reward)


class Executor:
    def __init__(self, registry: ToolRegistry, gate: HotBlock, store: KernelStore) -> None:
        self.registry = registry
        self.gate = gate
        self.store = store

    def execute(self, tool_name: str, payload: dict[str, Any], execution_id: str) -> dict[str, Any]:
        tool = self.registry.get(tool_name)
        # Serialize before side effects so malformed/non-JSON input cannot run.
        input_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        try:
            self.gate.check(tool_name)
            output = tool.handler(dict(payload))
            output_json = json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False)
            artifact = self.store.record_artifact(execution_id, tool_name, "succeeded", input_json, output_json, None)
            return {"execution_id": execution_id, "status": "succeeded", "tool": tool_name,
                    "output": json.loads(output_json), "artifact": artifact}
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            artifact = self.store.record_artifact(execution_id, tool_name, "failed", input_json, None, error)
            return {"execution_id": execution_id, "status": "failed", "tool": tool_name,
                    "error": error, "artifact": artifact}


class AgentRuntimeKernel:
    """One coherent selection -> policy gate -> execution -> artifact -> reward runtime."""

    def __init__(self, database: str | Path, seed: int | None = None) -> None:
        self.store = KernelStore(database)
        self.registry = ToolRegistry()
        self.hotblock = HotBlock(self.store)
        self.policy = BanditPolicy(self.store, seed=seed)
        self.executor = Executor(self.registry, self.hotblock, self.store)

    def register_tool(self, name: str, handler: Callable[[dict[str, Any]], Any], description: str = "") -> None:
        self.registry.register(name, handler, description)

    def run(self, payload: dict[str, Any], tool_name: str | None = None, execution_id: str | None = None) -> dict[str, Any]:
        if not self.registry.names():
            raise KernelError("register at least one tool before running")
        selected = tool_name or self.policy.select(self.registry.names())
        # Unknown tool names fail before any execution.
        self.registry.get(selected)
        identifier = execution_id or hashlib.sha256(
            f"{time.time_ns()}:{selected}:{random.getrandbits(128)}".encode()
        ).hexdigest()
        return self.executor.execute(selected, payload, identifier)

    def reward(self, execution_id: str, value: float) -> dict[str, Any]:
        return self.policy.update(execution_id, value)
