"""
Assignment 11 — Audit Log starter (TODO).

Records every interaction for forensics. Never blocks by itself —
other layers catch attacks; this layer makes them reviewable.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path


def default_audit_log_path() -> str:
    """Always resolve to <repo>/outputs/… (safe when cwd is src/)."""
    repo_root = Path(__file__).resolve().parents[2]
    return str(repo_root / "outputs" / "audit_log.json")


class AuditLogPlugin:
    """Framework-agnostic audit logger (wire into ADK callbacks or your pipeline)."""

    def __init__(self):
        self.name = "audit_log"
        self.logs: list[dict] = []
        self._open: dict[str, tuple[float, str, str, str]] = {}

    def record_input(self, *, user_id: str, text: str, request_id: str | None = None):
        """Store an input and its start time, keyed by request or user ID."""
        key = request_id or user_id
        self._open[key] = (time.perf_counter(), utc_now_iso(), user_id, text)
        return key

    def record_output(
        self,
        *,
        user_id: str,
        text: str,
        blocked: bool = False,
        layer: str | None = None,
        request_id: str | None = None,
    ):
        """Store the final decision, including latency and any blocking layer."""
        key = request_id or user_id
        started = self._open.pop(key, None)
        finished_at = utc_now_iso()
        if started is None:
            start_time, started_at, input_user, input_text = (
                time.perf_counter(),
                finished_at,
                user_id,
                "",
            )
        else:
            start_time, started_at, input_user, input_text = started

        self.logs.append(
            {
                "request_id": key,
                "user_id": input_user,
                "input": input_text,
                "output": text,
                "blocked": blocked,
                "layer": layer,
                "started_at": started_at,
                "finished_at": finished_at,
                "latency_ms": round((time.perf_counter() - start_time) * 1000, 3),
            }
        )

    def export_json(self, filepath: str | None = None):
        """Write logs to disk (JSON array) under repo-root ``outputs/`` by default."""
        path = Path(filepath or default_audit_log_path())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.logs, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return str(path)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
