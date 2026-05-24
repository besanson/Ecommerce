from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from gacct.domain.decisions import DecisionRecord
from gacct.domain.trace import TraceEvent


class TraceStore:
    """Append-only JSONL store, one file per scenario.

    The store records two kinds of artifacts in a single stream:
      * decision events (`event_type="decision"`) wrapping a DecisionRecord
      * context events (mission_opened, offer_received, approval_requested,
        approval_decided, scenario_completed)

    Each event carries a `prev_hash` and `self_hash` to chain a scenario's
    history. This is a demo mechanism — see docs/risk-and-limitations.md.
    Production non-repudiation would need signed records and an external
    timestamp authority.
    """

    def __init__(self, base_dir: str | Path):
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        self._sequence: Dict[str, int] = {}
        self._last_hash: Dict[str, Optional[str]] = {}
        self._events: Dict[str, List[TraceEvent]] = {}

    # ---- writes ----------------------------------------------------------

    def record_event(
        self,
        *,
        scenario_id: str,
        event_type: str,
        actor: str,
        summary: str,
        detail: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> TraceEvent:
        seq = self._sequence.get(scenario_id, 0) + 1
        self._sequence[scenario_id] = seq
        prev = self._last_hash.get(scenario_id)
        event = TraceEvent(
            trace_id=trace_id or f"{scenario_id}-{seq:04d}",
            scenario_id=scenario_id,
            sequence=seq,
            event_type=event_type,
            actor=actor,
            summary=summary,
            detail=detail or {},
            prev_hash=prev,
        )
        event.self_hash = self._hash(event)
        self._last_hash[scenario_id] = event.self_hash
        self._append(event)
        return event

    def record_decision(self, record: DecisionRecord) -> TraceEvent:
        return self.record_event(
            scenario_id=record.scenario_id,
            event_type="decision",
            actor=record.actor,
            summary=f"{record.intended_action} -> {record.decision.value}",
            detail=json.loads(record.model_dump_json()),
            trace_id=record.trace_id,
        )

    # ---- reads -----------------------------------------------------------

    def events_for(self, scenario_id: str) -> List[TraceEvent]:
        return list(self._events.get(scenario_id, []))

    def decision_records(self, scenario_id: str) -> List[DecisionRecord]:
        out: List[DecisionRecord] = []
        for ev in self.events_for(scenario_id):
            if ev.event_type == "decision":
                out.append(DecisionRecord.model_validate(ev.detail))
        return out

    def all_scenarios(self) -> List[str]:
        return sorted(self._events.keys())

    # ---- persistence -----------------------------------------------------

    def _path_for(self, scenario_id: str) -> Path:
        safe = scenario_id.replace("/", "_")
        return self._base / f"{safe}.jsonl"

    def _append(self, event: TraceEvent) -> None:
        self._events.setdefault(event.scenario_id, []).append(event)
        path = self._path_for(event.scenario_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(event.model_dump_json())
            f.write("\n")

    @staticmethod
    def _hash(event: TraceEvent) -> str:
        payload = {
            "scenario_id": event.scenario_id,
            "sequence": event.sequence,
            "event_type": event.event_type,
            "actor": event.actor,
            "summary": event.summary,
            "detail": event.detail,
            "prev_hash": event.prev_hash,
            "timestamp": event.timestamp.isoformat(),
        }
        blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    # ---- loading existing files -----------------------------------------

    @classmethod
    def load(cls, base_dir: str | Path) -> "TraceStore":
        store = cls(base_dir)
        for jsonl in sorted(Path(base_dir).glob("*.jsonl")):
            with jsonl.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    event = TraceEvent.model_validate_json(line)
                    store._events.setdefault(event.scenario_id, []).append(event)
                    store._sequence[event.scenario_id] = max(
                        store._sequence.get(event.scenario_id, 0), event.sequence
                    )
                    store._last_hash[event.scenario_id] = event.self_hash
        return store

    @staticmethod
    def iter_events_file(path: str | Path) -> Iterable[TraceEvent]:
        with Path(path).open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield TraceEvent.model_validate_json(line)
