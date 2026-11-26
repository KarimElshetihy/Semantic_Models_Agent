"""SQLite log of approval transitions and refused attempts. The log is the source of truth.

The current state of a run is the target of its last transition. Each payload is
stored with its SHA-256 so tampering can be detected with verify_integrity().
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from ssas_agent.approval.proposal import canonical_json
from ssas_agent.approval.states import Action, State
from ssas_agent.bim.document import sha256_hex
from ssas_agent.clock import utc_now_iso
from ssas_agent.policy import Operation, PathPolicy

SCHEMA = """
CREATE TABLE IF NOT EXISTS transitions (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_transitions_run ON transitions (run_id, seq);
CREATE TABLE IF NOT EXISTS attempts (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    outcome TEXT NOT NULL,
    reason TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_attempts_run ON attempts (run_id, seq);
"""


class WorkflowStore:
    def __init__(self, policy: PathPolicy, db_path: Path) -> None:
        self._db_path = policy.enforce(Operation.WRITE, db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._execute_script(SCHEMA)

    @property
    def db_path(self) -> Path:
        return self._db_path

    def current_state(self, run_id: str) -> State | None:
        rows = self._fetch_all(
            "SELECT to_state FROM transitions WHERE run_id = ? ORDER BY seq DESC LIMIT 1",
            (run_id,),
        )
        return State(rows[0][0]) if rows else None

    def append_transition(
        self,
        run_id: str,
        from_state: State | None,
        to_state: State,
        action: Action,
        actor: str,
        payload: dict[str, Any],
    ) -> None:
        payload_json = canonical_json(payload)
        self._execute(
            "INSERT INTO transitions (run_id, from_state, to_state, action, actor, recorded_at,"
            " payload_json, payload_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                from_state.value if from_state is not None else None,
                to_state.value,
                action.value,
                actor,
                utc_now_iso(),
                payload_json,
                sha256_hex(payload_json.encode("utf-8")),
            ),
        )

    def last_payload(self, run_id: str, action: Action) -> dict[str, Any] | None:
        rows = self._fetch_all(
            "SELECT payload_json FROM transitions WHERE run_id = ? AND action = ? ORDER BY seq DESC LIMIT 1",
            (run_id, action.value),
        )
        return json.loads(rows[0][0]) if rows else None

    def transitions(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._fetch_all(
            "SELECT from_state, to_state, action, actor, payload_sha256 FROM transitions"
            " WHERE run_id = ? ORDER BY seq",
            (run_id,),
        )
        keys = ("from_state", "to_state", "action", "actor", "payload_sha256")
        return [dict(zip(keys, row)) for row in rows]

    def record_attempt(self, run_id: str, action: Action, actor: str, outcome: str, reason: str) -> None:
        self._execute(
            "INSERT INTO attempts (run_id, action, actor, outcome, reason, recorded_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, action.value, actor, outcome, reason, utc_now_iso()),
        )

    def attempts(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._fetch_all(
            "SELECT action, actor, outcome, reason FROM attempts WHERE run_id = ? ORDER BY seq",
            (run_id,),
        )
        keys = ("action", "actor", "outcome", "reason")
        return [dict(zip(keys, row)) for row in rows]

    def verify_integrity(self, run_id: str) -> bool:
        """True when every stored payload still matches its recorded SHA-256."""
        rows = self._fetch_all(
            "SELECT payload_json, payload_sha256 FROM transitions WHERE run_id = ?",
            (run_id,),
        )
        return all(sha256_hex(payload_json.encode("utf-8")) == digest for payload_json, digest in rows)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(sql, params)

    def _execute_script(self, script: str) -> None:
        with closing(self._connect()) as connection, connection:
            connection.executescript(script)

    def _fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        with closing(self._connect()) as connection:
            return connection.execute(sql, params).fetchall()
