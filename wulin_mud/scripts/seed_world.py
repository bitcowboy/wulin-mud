"""Load every seed YAML file into the SQLite world database.

Run with::

    python -m wulin_mud.scripts.seed_world

What this script does:

1. Discover every ``*.yaml`` under three subdirectories of
   ``wulin_mud/world/seed_data/``:
     - ``npcs/``       — one NPC per file (mapping at the root)
     - ``locations/``  — multiple locations per file (list at the root)
     - ``items/``      — multiple items per file (list at the root)
2. Validate each entry against its pydantic model. Any error aborts
   the script with a non-zero exit code.
3. Cross-check that the NPC↔NPC relationship graph is bidirectional.
4. Initialise the SQLite schema and write everything in one transaction.

Upsert semantics:

- **NPCs** and **Locations** upsert. YAML is the source of truth for
  their definitions, so editing a YAML and re-running picks up changes.
- **Items** and **PlayerState** are *insert-only*. They have runtime
  state — item ownership, player wealth/inventory — that re-seeding
  must not stomp. To start over, delete the SQLite file and re-seed.

The YAML format for NPCs follows ``docs/npc-spec.md``. Locations and
items are 1:1 with their pydantic models (no field renaming needed —
both are simpler than NPC).
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import yaml
from sqlmodel import Session

from wulin_mud.ontology import NPC, PLAYER_ID, Item, Location, PlayerState
from wulin_mud.world.persistence import (
    ItemRow,
    PlayerStateRow,
    get_engine,
    init_db,
    item_to_row,
    location_to_row,
    player_state_to_row,
    save_npc,
)

SEED_DATA_DIR = Path(__file__).resolve().parents[1] / "world" / "seed_data"
SEED_NPCS_DIR = SEED_DATA_DIR / "npcs"
SEED_LOCATIONS_DIR = SEED_DATA_DIR / "locations"
SEED_ITEMS_DIR = SEED_DATA_DIR / "items"

# Player defaults (from docs/world-setting.md §4).
PLAYER_START_LOCATION = "loc_pier"
PLAYER_START_WEALTH = 50


# ---------------------------------------------------------------------------
# NPC loader (was the original sprint A work; unchanged below)
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


def load_npc_yaml(path: Path) -> NPC:
    """Load and validate a single NPC seed YAML file."""
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
# Location loader (list-at-root YAML)
# ---------------------------------------------------------------------------


def load_locations_yaml(path: Path) -> list[Location]:
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise TypeError(f"Locations YAML root must be a list, got {type(raw).__name__} in {path}")
    return [Location.model_validate(item) for item in raw]


def discover_location_seed_files(seed_dir: Path = SEED_LOCATIONS_DIR) -> list[Path]:
    if not seed_dir.exists():
        return []
    return sorted(p for p in seed_dir.glob("*.yaml") if p.is_file())


def load_all_locations(seed_dir: Path = SEED_LOCATIONS_DIR) -> list[Location]:
    locations: list[Location] = []
    for path in discover_location_seed_files(seed_dir):
        locations.extend(load_locations_yaml(path))
    return locations


# ---------------------------------------------------------------------------
# Item loader (list-at-root YAML)
# ---------------------------------------------------------------------------


def load_items_yaml(path: Path) -> list[Item]:
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise TypeError(f"Items YAML root must be a list, got {type(raw).__name__} in {path}")
    return [Item.model_validate(item) for item in raw]


def discover_item_seed_files(seed_dir: Path = SEED_ITEMS_DIR) -> list[Path]:
    if not seed_dir.exists():
        return []
    return sorted(p for p in seed_dir.glob("*.yaml") if p.is_file())


def load_all_items(seed_dir: Path = SEED_ITEMS_DIR) -> list[Item]:
    items: list[Item] = []
    for path in discover_item_seed_files(seed_dir):
        items.extend(load_items_yaml(path))
    return items


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
    files added later.
    """
    loaded_ids = {n.id for n in npcs}
    rel_by_npc = {n.id: set(n.relationships.keys()) for n in npcs}

    missing: list[str] = []
    for npc in npcs:
        for other_id in npc.relationships:
            if other_id not in loaded_ids:
                continue
            if npc.id not in rel_by_npc.get(other_id, set()):
                missing.append(
                    f"  {npc.id} -> {other_id}: present, but reverse edge "
                    f"{other_id} -> {npc.id} is missing"
                )

    if missing:
        raise RelationshipSymmetryError(
            "Relationship graph is not bidirectionally consistent:\n" + "\n".join(missing)
        )


# ---------------------------------------------------------------------------
# Write to DB
# ---------------------------------------------------------------------------


def seed_database(
    *,
    npcs: Iterable[NPC],
    locations: Iterable[Location] = (),
    items: Iterable[Item] = (),
    init_player: bool = True,
    db_url: str | None = None,
) -> None:
    """Initialise the schema and write seed entities in one transaction.

    See module docstring for upsert vs insert-only semantics.
    """
    engine = get_engine(db_url=db_url)
    init_db(engine)
    with Session(engine) as session:
        for npc in npcs:
            save_npc(session, npc)
        for loc in locations:
            session.merge(location_to_row(loc))
        for item in items:
            if session.get(ItemRow, item.id) is None:
                session.add(item_to_row(item))
        if init_player and session.get(PlayerStateRow, PLAYER_ID) is None:
            session.add(
                player_state_to_row(
                    PlayerState(
                        current_location_id=PLAYER_START_LOCATION,
                        wealth=PLAYER_START_WEALTH,
                    )
                )
            )
        session.commit()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(*, db_url: str | None = None) -> int:
    # NPCs
    npc_files = discover_npc_seed_files()
    if not npc_files:
        print(f"No NPC seed YAMLs found under {SEED_NPCS_DIR}", file=sys.stderr)
        return 1

    npcs: list[NPC] = []
    for path in npc_files:
        try:
            npc = load_npc_yaml(path)
        except Exception as exc:
            print(f"Failed to load NPC {path}: {exc}", file=sys.stderr)
            return 2
        npcs.append(npc)
        print(f"  loaded NPC {npc.id} ({npc.name}) from {path.name}")

    try:
        check_relationship_symmetry(npcs)
    except RelationshipSymmetryError as exc:
        print(f"Relationship symmetry check failed:\n{exc}", file=sys.stderr)
        return 3

    # Locations
    locations: list[Location] = []
    for path in discover_location_seed_files():
        try:
            locs = load_locations_yaml(path)
        except Exception as exc:
            print(f"Failed to load locations {path}: {exc}", file=sys.stderr)
            return 4
        locations.extend(locs)
        print(f"  loaded {len(locs)} location(s) from {path.name}")

    # Items
    items: list[Item] = []
    for path in discover_item_seed_files():
        try:
            its = load_items_yaml(path)
        except Exception as exc:
            print(f"Failed to load items {path}: {exc}", file=sys.stderr)
            return 5
        items.extend(its)
        print(f"  loaded {len(its)} item(s) from {path.name}")

    seed_database(npcs=npcs, locations=locations, items=items, db_url=db_url)
    print(
        f"Seeded {len(npcs)} NPC(s), {len(locations)} location(s), "
        f"{len(items)} item(s) (player initialised if missing) into the database."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
