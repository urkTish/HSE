# ruff: noqa: S608  # identifiers come from pg_catalog and are quoted by _q; values are bound
"""Hard delete of a whole project and everything that belongs to it (D-265).

The schema has ~1,000 foreign keys and almost none cascade, so the rows to delete are found
by walking the live foreign-key graph from ``projects`` instead of a hand-kept table list
that would go stale with every module:

* a NOT NULL reference to a deleted row means the referencing row belongs to it: delete it too;
* a nullable reference only links to it: set it to NULL and keep the row, except for the
  project-owned tables in ``FORCE_DELETE`` whose nullable ``project_id`` scopes the row (a role
  assignment with its project nulled would become an organisation-wide role).

Rows are tracked by ``ctid`` (a few tables have composite primary keys); every statement runs in
the caller's transaction, so a failure leaves nothing half-deleted. ``audit_log`` has no foreign
key to project data and is append-only, so the project's audit history stays.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

# Nullable project references that still mean "this row belongs to the project".
FORCE_DELETE = frozenset(
    {
        ("role_assignments", "project_id"),
        ("env_permits", "project_id"),
        ("fu_effectiveness_checks", "project_id"),
        ("fu_lesson_links", "project_id"),
        ("rp_packs", "project_id"),
        ("sc_profiles", "project_id"),
        ("xp_subscriptions", "project_id"),
        ("xp_jobs", "project_id"),
    }
)


@dataclass(frozen=True)
class _Fk:
    child: str
    child_col: str
    parent: str
    parent_col: str
    nullable: bool


def _foreign_keys(db: Session) -> dict[str, list[_Fk]]:
    rows = db.execute(
        text(
            """
            SELECT c.conrelid::regclass::text, ca.attname, c.confrelid::regclass::text,
                   pa.attname, NOT ca.attnotnull
            FROM pg_constraint c
            JOIN pg_attribute ca ON ca.attrelid = c.conrelid AND ca.attnum = c.conkey[1]
            JOIN pg_attribute pa ON pa.attrelid = c.confrelid AND pa.attnum = c.confkey[1]
            WHERE c.contype = 'f' AND c.connamespace = 'public'::regnamespace
              AND array_length(c.conkey, 1) = 1
            """
        )
    ).all()
    by_parent: dict[str, list[_Fk]] = defaultdict(list)
    for child, ccol, parent, pcol, nullable in rows:
        by_parent[parent].append(_Fk(child, ccol, parent, pcol, nullable))
    return by_parent


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


@dataclass
class Purge:
    deleted: dict[str, int] = field(default_factory=dict)
    # Copies of the deleted rows per table (D-271), None when over the snapshot limit.
    rows: dict[str, list[dict[str, Any]]] | None = None


def purge_project(db: Session, project_id: uuid.UUID) -> dict[str, int]:
    """Delete the project and its data; returns rows deleted per table (non-zero only)."""
    return purge(db, "projects", project_id).deleted


PURGE_LOCK_KEY = 7_265_271  # one purge at a time (D-265 / D-271)


def _composite_fk_parents(db: Session) -> set[str]:
    return set(
        db.scalars(
            text(
                "SELECT DISTINCT confrelid::regclass::text FROM pg_constraint "
                "WHERE contype = 'f' AND connamespace = 'public'::regnamespace "
                "AND array_length(conkey, 1) > 1"
            )
        ).all()
    )


def _drop_site_ids(db: Session, site_ids: list[object]) -> None:
    """ARRAY columns carry no foreign key: strip deleted sites from every ``site_ids`` array."""
    tables = db.scalars(
        text(
            "SELECT table_name FROM information_schema.columns WHERE table_schema = 'public' "
            "AND column_name = 'site_ids' AND data_type = 'ARRAY'"
        )
    ).all()
    for t in tables:
        db.execute(
            text(
                f"UPDATE {_q(t)} SET site_ids = COALESCE("
                "(SELECT array_agg(x) FROM unnest(site_ids) AS x WHERE NOT x = ANY(:ids)), "
                "'{}') WHERE site_ids && :ids"
            ),
            {"ids": list(site_ids)},
        )


def purge(db: Session, root: str, row_id: object, snapshot_limit: int = 0) -> Purge:
    """Delete one row of ``root`` (by ``id``) and everything that belongs to it."""
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": PURGE_LOCK_KEY})
    fks = _foreign_keys(db)
    doomed: dict[str, set[str]] = defaultdict(set)
    # (table, column) -> referenced values to null out. Values, not ctids: an UPDATE moves a
    # row's ctid, and one table can be unlinked through several columns.
    unlink: dict[tuple[str, str], set[object]] = defaultdict(set)

    start = db.scalars(
        text(f"SELECT ctid::text FROM {_q(root)} WHERE id = :id"), {"id": row_id}
    ).all()
    doomed[root].update(start)
    queue: list[tuple[str, set[str]]] = [(root, set(start))]
    while queue:
        table, ctids = queue.pop()
        for fk in fks.get(table, []):
            values = db.scalars(
                text(
                    f"SELECT DISTINCT {_q(fk.parent_col)} FROM {_q(table)} "
                    "WHERE ctid = ANY(CAST(:t AS tid[]))"
                ),
                {"t": list(ctids)},
            ).all()
            if not values:
                continue
            forced = root == "projects" and (fk.child, fk.child_col) in FORCE_DELETE
            if fk.nullable and not forced:
                unlink[(fk.child, fk.child_col)].update(values)
                continue
            found = set(
                db.scalars(
                    text(
                        f"SELECT ctid::text FROM {_q(fk.child)} WHERE {_q(fk.child_col)} = ANY(:v)"
                    ),
                    {"v": list(values)},
                ).all()
            )
            new = found - doomed[fk.child]
            if new:
                doomed[fk.child].update(new)
                queue.append((fk.child, new))

    composite = _composite_fk_parents(db) & {t for t, c in doomed.items() if c}
    if composite:
        raise RuntimeError(f"Composite foreign keys reference {sorted(composite)}; not supported")
    doomed_sites: list[object] = []
    if doomed.get("sites"):
        doomed_sites = list(
            db.scalars(
                text("SELECT id FROM sites WHERE ctid = ANY(CAST(:t AS tid[]))"),
                {"t": list(doomed["sites"])},
            ).all()
        )
    out = Purge()
    total = sum(len(c) for c in doomed.values())
    if snapshot_limit and total <= snapshot_limit:
        out.rows = {
            t: list(
                db.scalars(
                    text(
                        f"SELECT row_to_json(x)::jsonb FROM {_q(t)} x "
                        "WHERE x.ctid = ANY(CAST(:t AS tid[]))"
                    ),
                    {"t": list(c)},
                ).all()
            )
            for t, c in doomed.items()
            if c
        }

    # Unlink the rows that stay (doomed rows are not updated here, so their ctids hold).
    for (table, col), refs in unlink.items():
        db.execute(
            text(
                f"UPDATE {_q(table)} SET {_q(col)} = NULL WHERE {_q(col)} = ANY(:v) "
                "AND NOT ctid = ANY(CAST(:t AS tid[]))"
            ),
            {"v": list(refs), "t": list(doomed.get(table, set()))},
        )

    # Delete children before parents: a table goes once no other pending table still references
    # it. Self references are fine within one DELETE statement. A cycle is broken by nulling a
    # nullable reference on the doomed rows (RETURNING keeps their new ctids).
    pending = {t for t, c in doomed.items() if c}
    edges = {fk for fk_list in fks.values() for fk in fk_list}
    deleted = out.deleted
    while pending:
        live = [fk for fk in edges if fk.child in pending and fk.parent in pending]
        ready = [t for t in pending if not any(fk.parent == t and fk.child != t for fk in live)]
        if not ready:
            breakable = [fk for fk in live if fk.nullable and fk.child != fk.parent]
            if not breakable:
                raise RuntimeError(f"Cyclic required references between {sorted(pending)}")
            for fk in breakable:
                doomed[fk.child] = set(
                    db.scalars(
                        text(
                            f"UPDATE {_q(fk.child)} SET {_q(fk.child_col)} = NULL "
                            "WHERE ctid = ANY(CAST(:t AS tid[])) RETURNING ctid::text"
                        ),
                        {"t": list(doomed[fk.child])},
                    ).all()
                )
                edges.discard(fk)
            continue
        for t in ready:
            result = db.execute(
                text(f"DELETE FROM {_q(t)} WHERE ctid = ANY(CAST(:t AS tid[]))"),
                {"t": list(doomed[t])},
            )
            deleted[t] = result.rowcount  # type: ignore[attr-defined]
            pending.discard(t)
    if doomed_sites:
        _drop_site_ids(db, doomed_sites)
    return out
