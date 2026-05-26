"""Load seed YAML files into the SQLite world database.

Run with::

    python -m wulin_mud.scripts.seed_world

What this script does:

1. Discover every ``*.yaml`` under ``wulin_mud/world/seed_data/npcs/``.
2. Validate each file against the NPC pydantic model
   (raising loudly on the first failure).
3. Cross-check that the NPC↔NPC relationship graph is bidirectional —
   if A names B in its ``initial_relationships`` map but B does not name
   A, that is a seed error and the script aborts.
4. Initialise the SQLite schema (``init_db``) and upsert every NPC and
   its relationships in one transaction.

The YAML format follows ``docs/npc-spec.md``. The field-name mapping
from YAML to the pydantic NPC model is intentionally narrow; see
``_yaml_to_npc_payload`` for the exact translation rules.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import yaml
from sqlmodel import Session

from wulin_mud.ontology import NPC
from wulin_mud.world.persistence import get_engine, init_db, save_npc


SEED_NPCS_DIR = Path(__file__).resolve().parents[1] / "world" / "seed_data" / "npcs"


# ---------------------------------------------------------------------------
# YAML -> pydantic payload mapping
# ---------------------------------------------------------------------------


def _yaml_to_npc_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Translate the YAML seed format into the NPC pydantic payload.

    The translations applied here are:

    - ``initial_relationships`` → ``relationships``, with the YAML dict
      key promoted to ``other_id`` and the inner ``type`` / ``label``
      fields renamed to ``relationship_type`` / ``relationship_label``.
    - ``initial_knowledge`` → ``knowledge``.
    - ``initial_heard_rumors`` → ``heard_rumors``.

    Every other top-level key is passed through unchanged. Unknown keys
    will be rejected by pydantic (``extra="forbid"`` on NPC), which is
    intended — that surfaces schema drift between YAML and the model.
    """
    if not isinstance(raw, dict):
        raise TypeError(f"NPC YAML root must be a mapping, got {type(raw).__name__}")

    payload: dict[str, Any] = {}

    for key, value in raw.items():
        if key == "initial_relationships":
            payload["relationships"] = _translate_relationships(value)
        elif key == "initial_knowledge":
            payload["knowledge"] = value
        elif key == "initial_heard_rumors":
            payload["heard_rumors"] = value
        else:
            payload[key] = value

    return payload


def _translate_relationships(raw: Any) -> dict[str, dict[str, Any]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise TypeError(
            f"initial_relationships must be a mapping of other_id -> details, "
            f"got {type(raw).__name__}"
        )
    result: dict[str, dict[str, Any]] = {}
    for other_id, details in raw.items():
        if not isinstance(details, dict):
            raise TypeError(
                f"relationship entry for {other_id!r} must be a mapping, "
                f"got {type(details).__name__}"
            )
        translated: dict[str, Any] = {"other_id": other_id}
        for k, v in details.items():
            if k == "type":
                translated["relationship_type"] = v
            elif k == "label":
                translated["relationship_label"] = v
            else:
                translated[k] = v
        result[other_id] = translated
    return result


# ---------------------------------------------------------------------------
# Load + validate
# ---------------------------------------------------------------------------


def load_npc_yaml(path: Path) -> NPC:
    """Load and validate a single NPC seed YAML file.

    Any validation failure raises pydantic's ``ValidationError``, which
    the caller is expected to propagate (this script aborts on the
    first such error).
    """
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    payload = _yaml_to_npc_payload(raw)
    return NPC.model_validate(payload)


def discover_npc_seed_files(seed_dir: Path = SEED_NPCS_DIR) -> list[Path]:
    if not seed_dir.exists():
        return []
    return sorted(p for p in seed_dir.glob("*.yaml") if p.is_file())


def load_all_npcs(seed_dir: Path = SEED_NPCS_DIR) -> list[NPC]:
    return [load_npc_yaml(p) for p in discover_npc_seed_files(seed_dir)]


# ---------------------------------------------------------------------------
# Relationship symmetry check
# ---------------------------------------------------------------------------


class RelationshipSymmetryError(ValueError):
    """Raised when the NPC relationship graph is not bidirectionally consistent."""


def check_relationship_symmetry(npcs: Sequence[NPC]) -> None:
    """Ensure every relationship has its mirror.

    If ``npc_a`` names ``npc_b`` in its relationships dict, ``npc_b``
    must in turn name ``npc_a``. We don't require numerical symmetry
    (A may like B more than B likes A), only that the edge exists in
    both directions.

    Relationships pointing at NPCs that are not part of the loaded
    seed set are tolerated — they may be filled in by other seed
    files added later. We only flag *one-sided* edges between NPCs
    that are both loaded.
    """
    loaded_ids = {n.id for n in npcs}
    rel_by_npc = {n.id: set(n.relationships.keys()) for n in npcs}

    missing: list[str] = []
    for npc in npcs:
        for other_id in npc.relationships:
            if other_id not in loaded_ids:
                continue  # mirror may live in a later seed file
            if npc.id not in rel_by_npc.get(other_id, set()):
                missing.append(
                    f"  {npc.id} -> {other_id}: present, but reverse edge "
                    f"{other_id} -> {npc.id} is missing"
                )

    if missing:
        raise RelationshipSymmetryError(
            "Relationship graph is not bidirectionally consistent:\n"
            + "\n".join(missing)
        )


# ---------------------------------------------------------------------------
# Write to DB
# ---------------------------------------------------------------------------


def seed_database(npcs: Iterable[NPC], *, db_url: str | None = None) -> None:
    """Initialise the schema and upsert all NPCs in one transaction."""
    engine = get_engine(db_url=db_url)
    init_db(engine)
    with Session(engine) as session:
        for npc in npcs:
            save_npc(session, npc)
        session.commit()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(seed_dir: Path = SEED_NPCS_DIR, *, db_url: str | None = None) -> int:
    files = discover_npc_seed_files(seed_dir)
    if not files:
        print(f"No NPC seed YAMLs found under {seed_dir}", file=sys.stderr)
        return 1

    npcs: list[NPC] = []
    for path in files:
        try:
            npc = load_npc_yaml(path)
        except Exception as exc:
            print(f"Failed to load {path}: {exc}", file=sys.stderr)
            return 2
        npcs.append(npc)
        print(f"  loaded {npc.id} ({npc.name}) from {path.name}")

    try:
        check_relationship_symmetry(npcs)
    except RelationshipSymmetryError as exc:
        print(f"Relationship symmetry check failed:\n{exc}", file=sys.stderr)
        return 3

    seed_database(npcs, db_url=db_url)
    print(f"Seeded {len(npcs)} NPC(s) into the database.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
