"""Imported records are provenance-bearing data, never executable authority."""

import csv
import json
from pathlib import Path
from typing import Literal, Protocol

from pydantic import Field, JsonValue, model_validator

from .core.audit import connect, digest
from .core.contracts import Assessment, Decision, Disposition, Evidence, Proposal, Record, Review


class HistoricalDecision(Record):
    source: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_revision: str | None = None
    proposal: Proposal
    decision_at: float | None = None
    available_at: float | None = None
    evidence: Evidence | None = None
    evidence_available_at: float | None = None
    assessment: Assessment | None = None
    historical_decision: Decision | None = None
    outcome: dict[str, JsonValue] | None = None
    outcome_available_at: float | None = None
    review: Review | None = None
    review_available_at: float | None = None
    usage: dict[str, int] | None = None
    policy_version: str | None = None
    groups: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def nonnegative_usage(self):
        if self.usage is not None and any(v < 0 for v in self.usage.values()):
            raise ValueError("Resource usage cannot be negative")
        return self


class ExpectedLabels(Record):
    disposition: Disposition | None = None
    signals: dict[str, str | float] = Field(default_factory=dict)


class HistoryMapper(Protocol):
    def __call__(self, row: dict) -> HistoricalDecision: ...


class FieldMapper:
    """Map source dotted paths into contract paths; JSON cell decoding is explicit."""

    def __init__(
        self,
        fields: dict[str, str],
        *,
        json_fields: list[str] | None = None,
        constants: dict | None = None,
    ):
        self.fields, self.json_fields, self.constants = (
            fields,
            set(json_fields or []),
            constants or {},
        )

    def __call__(self, row: dict) -> HistoricalDecision:
        output = json.loads(json.dumps(self.constants))
        for destination, source in self.fields.items():
            value = row
            for key in source.split("."):
                if not isinstance(value, dict) or key not in value:
                    raise ValueError(f"Missing mapped field: {source}")
                value = value[key]
            if destination in self.json_fields and isinstance(value, str):
                value = json.loads(value)
            target = output
            parts = destination.split(".")
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = value
        return HistoricalDecision.model_validate(output)


def content_key(record: HistoricalDecision) -> str:
    # Deliberately excludes source IDs, timestamps, labels and outcomes.
    proposal = record.proposal.model_dump(mode="json")
    proposal["message"] = " ".join(record.proposal.message.casefold().split())
    return digest(proposal)


class SnapshotCase(Record):
    id: str
    content_hash: str
    record: HistoricalDecision
    labels: ExpectedLabels | None = None
    annotation: dict[str, JsonValue] | None = None
    split: Literal["development", "validation", "evaluation"]


class DatasetSnapshot(Record):
    name: str
    cases: list[SnapshotCase]
    group_by: str | None = None
    development_informed: bool = False
    informed_reason: str | None = None
    parent_hash: str | None = None
    hash: str = ""

    @model_validator(mode="after")
    def validate_memberships(self):
        seen: set[str] = set()
        content: dict[str, str] = {}
        groups: dict[str, str] = {}
        for case in self.cases:
            if case.id in seen:
                raise ValueError("Duplicate record membership")
            seen.add(case.id)
            if case.content_hash != content_key(case.record):
                raise ValueError("Case content hash mismatch")
            for key in (
                case.content_hash,
                digest({"source": case.record.source, "source_id": case.record.source_id}),
            ):
                if key in content and content[key] != case.split:
                    raise ValueError("Duplicate content or source identity across splits")
                content[key] = case.split
            if self.group_by:
                group = case.record.groups.get(self.group_by)
                if group is None:
                    raise ValueError(f"Missing grouping field: {self.group_by}")
                if group in groups and groups[group] != case.split:
                    raise ValueError("Group crosses dataset splits")
                groups[group] = case.split
        if self.development_informed and not self.informed_reason:
            raise ValueError("Development-informed datasets require a reason")
        expected = digest(self.model_dump(mode="json", exclude={"hash"}))
        if self.hash and self.hash != expected:
            raise ValueError("Dataset hash mismatch")
        object.__setattr__(self, "hash", expected)
        return self

    def coverage(self) -> dict:
        return {
            split: {
                "cases": sum(c.split == split for c in self.cases),
                "disposition_labels": sum(
                    c.split == split and c.labels is not None and c.labels.disposition is not None
                    for c in self.cases
                ),
            }
            for split in ("development", "validation", "evaluation")
        }

    def save(self, path: str | Path):
        # Revalidate nested mutable data before publishing an immutable artifact.
        snapshot = DatasetSnapshot.model_validate(self.model_dump(mode="json"))
        with Path(path).open("x", encoding="utf-8") as file:
            file.write(snapshot.model_dump_json(indent=2))

    @classmethod
    def load(cls, path: str | Path):
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))

    def mark_informed(self, reason: str):
        return DatasetSnapshot.model_validate(
            {
                **self.model_dump(),
                "hash": "",
                "parent_hash": self.hash,
                "development_informed": True,
                "informed_reason": reason,
            }
        )


class HistoryStore:
    def __init__(self, home: str | Path):
        home = Path(home)
        home.mkdir(parents=True, exist_ok=True)
        self.path = home / "history.db"
        db = connect(self.path)
        try:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS history (
              id TEXT PRIMARY KEY, source TEXT NOT NULL, source_id TEXT NOT NULL,
              source_revision TEXT NOT NULL, sequence INTEGER NOT NULL,
              previous_id TEXT, body_hash TEXT NOT NULL, body TEXT NOT NULL,
              UNIQUE(source,source_id,source_revision));
            CREATE TABLE IF NOT EXISTS annotations (
              id INTEGER PRIMARY KEY, record_id TEXT NOT NULL, reviewer TEXT NOT NULL,
              reason TEXT NOT NULL, available_at REAL NOT NULL, labels TEXT NOT NULL,
              FOREIGN KEY(record_id) REFERENCES history(id));
            """)
        finally:
            db.close()

    def import_file(
        self, path: str | Path, *, mapper: HistoryMapper | None = None, dry_run: bool = False
    ) -> dict:
        path = Path(path)
        rows, errors = [], []
        with path.open(encoding="utf-8-sig", newline="") as file:
            if path.suffix.lower() == ".csv":
                reader = csv.DictReader(file, strict=True)
                try:
                    fields = reader.fieldnames or []
                    if not fields or len(set(fields)) != len(fields):
                        errors.append({"row": 1, "error": "Missing or duplicate CSV headers"})
                    for row in reader:
                        if None in row or any(value is None for value in row.values()):
                            errors.append(
                                {"row": reader.line_num, "error": "CSV column count mismatch"}
                            )
                        else:
                            rows.append((reader.line_num, row))
                except csv.Error as exc:
                    errors.append({"row": reader.line_num, "error": "Malformed CSV: " + str(exc)})
            elif path.suffix.lower() == ".jsonl":
                for number, line in enumerate(file, 1):
                    if not line.strip():
                        continue
                    try:
                        rows.append((number, json.loads(line)))
                    except ValueError:
                        errors.append({"row": number, "error": "Invalid JSON"})
            else:
                raise ValueError("History inputs must be CSV or JSONL")
        return self._import(rows, mapper, dry_run, errors)

    def import_records(self, records: list[HistoricalDecision], *, dry_run=False) -> dict:
        return self._import(
            [(i, r.model_dump(mode="json")) for i, r in enumerate(records, 1)], None, dry_run, []
        )

    def _import(self, rows, mapper, dry_run, errors):
        validated = []
        for number, row in rows:
            try:
                record = mapper(row) if mapper else HistoricalDecision.model_validate(row)
                record = HistoricalDecision.model_validate(record.model_dump(mode="json"))
                body = record.model_dump(mode="json")
                validated.append((number, record, body, digest(body)))
            except Exception as exc:  # noqa: BLE001 -- report mapper failures; never silently skip
                errors.append({"row": number, "error": type(exc).__name__ + ": " + str(exc)})
        db = connect(self.path)
        created, duplicates, ids = 0, 0, []
        try:
            db.execute("BEGIN IMMEDIATE")
            for number, record, body, body_hash in validated:
                revision = (
                    record.source_revision if record.source_revision is not None else body_hash
                )
                old = db.execute(
                    "SELECT * FROM history WHERE source=? AND source_id=? AND source_revision=?",
                    (record.source, record.source_id, revision),
                ).fetchone()
                if old:
                    if old["body_hash"] != body_hash:
                        errors.append(
                            {"row": number, "error": "Conflicting content for source revision"}
                        )
                    else:
                        duplicates += 1
                        ids.append(old["id"])
                    continue
                previous = db.execute(
                    "SELECT id,sequence FROM history WHERE source=? AND source_id=? "
                    "ORDER BY sequence DESC LIMIT 1",
                    (record.source, record.source_id),
                ).fetchone()
                rid = digest(
                    {
                        "source": record.source,
                        "id": record.source_id,
                        "revision": revision,
                        "body_hash": body_hash,
                    }
                )
                db.execute(
                    "INSERT INTO history VALUES (?,?,?,?,?,?,?,?)",
                    (
                        rid,
                        record.source,
                        record.source_id,
                        revision,
                        previous["sequence"] + 1 if previous else 1,
                        previous["id"] if previous else None,
                        body_hash,
                        json.dumps(body),
                    ),
                )
                created += 1
                ids.append(rid)
            committed = not errors and not dry_run
            db.commit() if committed else db.rollback()
        finally:
            db.close()
        return {
            "rows": len(rows) + sum(e["error"] == "Invalid JSON" for e in errors),
            "valid": not errors,
            "dry_run": dry_run,
            "committed": committed,
            "would_create": created,
            "created": created if committed else 0,
            "duplicates": duplicates,
            "record_ids": ids if not errors else [],
            "errors": errors,
        }

    def inspect(self, record_id: str) -> dict:
        db = connect(self.path)
        try:
            row = db.execute("SELECT * FROM history WHERE id=?", (record_id,)).fetchone()
            if not row:
                raise ValueError("History record not found")
            return {
                **dict(row),
                "record": json.loads(row["body"]),
                "annotations": [
                    dict(r)
                    for r in db.execute(
                        "SELECT * FROM annotations WHERE record_id=? ORDER BY id", (record_id,)
                    )
                ],
            }
        finally:
            db.close()

    def annotate(
        self,
        record_id: str,
        labels: ExpectedLabels,
        *,
        reviewer: str,
        reason: str,
        available_at: float,
    ) -> int:
        if not reviewer.strip() or not reason.strip():
            raise ValueError("Reviewer and reason are required")
        digest({"available_at": available_at, "labels": labels.model_dump()})
        db = connect(self.path)
        try:
            cursor = db.execute(
                "INSERT INTO annotations(record_id,reviewer,reason,available_at,labels) "
                "VALUES (?,?,?,?,?)",
                (record_id, reviewer, reason, available_at, labels.model_dump_json()),
            )
            db.commit()
            assert cursor.lastrowid is not None
            return cursor.lastrowid
        finally:
            db.close()

    def snapshot(
        self, name: str, memberships: dict[str, list[str]], *, group_by: str | None = None
    ) -> DatasetSnapshot:
        if set(memberships) - {"development", "validation", "evaluation"}:
            raise ValueError("Unknown split")
        cases = []
        for split, ids in memberships.items():
            for rid in ids:
                stored = self.inspect(rid)
                record = HistoricalDecision.model_validate(stored["record"])
                annotation = stored["annotations"][-1] if stored["annotations"] else None
                cases.append(
                    SnapshotCase.model_validate(
                        {
                            "id": rid,
                            "record": record.model_dump(),
                            "content_hash": content_key(record),
                            "split": split,
                            "labels": json.loads(annotation["labels"]) if annotation else None,
                            "annotation": annotation,
                        }
                    )
                )
        return DatasetSnapshot(name=name, cases=cases, group_by=group_by)
