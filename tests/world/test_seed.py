"""End-to-end test of the seed_world loader against the real Granny Sun YAML."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from sqlmodel import Session

from wulin_mud.core.enums import RelationshipType
from wulin_mud.ontology import NPC
from wulin_mud.scripts.seed_world import (
    SEED_NPCS_DIR,
    RelationshipSymmetryError,
    check_relationship_symmetry,
    load_npc_yaml,
    main,
    seed_database,
)
from wulin_mud.world.persistence import get_engine, list_npc_ids, load_npc

SUN_POPO_YAML = SEED_NPCS_DIR / "sun_popo.yaml"


def test_sun_popo_yaml_loads_and_validates() -> None:
    npc = load_npc_yaml(SUN_POPO_YAML)
    assert npc.id == "npc_sun_popo"
    assert npc.name == "孙婆婆"
    assert npc.age == 52
    # Personality dimensions survive the yaml -> pydantic mapping
    assert npc.personality.honesty == 0.8
    assert npc.personality.loyalty == 0.9
    # YAML's `type` -> `relationship_type` and `label` -> `relationship_label`
    son_rel = npc.relationships["npc_xiao_man"]
    assert son_rel.relationship_type is RelationshipType.KIN
    assert son_rel.relationship_label == "独子"
    # YAML's other_id is sourced from the dict key
    assert son_rel.other_id == "npc_xiao_man"
    # initial_knowledge / initial_heard_rumors got translated
    assert any(f.id == "f_qinghe_geography" for f in npc.knowledge)
    assert npc.heard_rumors[0].credibility == 0.7
    # Goal coercion: bare yaml strings become Goal(content=...)
    assert npc.short_term_goals[0].content.startswith("今天卖出")


def test_sun_popo_writes_to_db_and_reads_back(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'seed.db'}"
    npc = load_npc_yaml(SUN_POPO_YAML)
    seed_database([npc], db_url=db_url)

    engine = get_engine(db_url=db_url)
    with Session(engine) as s:
        assert list_npc_ids(s) == ["npc_sun_popo"]
        loaded = load_npc(s, "npc_sun_popo")
    assert loaded is not None
    assert loaded == npc


def test_main_entrypoint_seeds_and_returns_zero(tmp_path: Path) -> None:
    """`python -m wulin_mud.scripts.seed_world` must succeed end-to-end."""
    db_url = f"sqlite:///{tmp_path / 'main.db'}"
    exit_code = main(db_url=db_url)
    assert exit_code == 0
    engine = get_engine(db_url=db_url)
    with Session(engine) as s:
        loaded = load_npc(s, "npc_sun_popo")
    assert loaded is not None
    assert loaded.role == "回春堂老板娘"


# ---------------------------------------------------------------------------
# Relationship symmetry tests
# ---------------------------------------------------------------------------


def _minimal_npc_payload(npc_id: str, name: str) -> dict[str, object]:
    return {
        "id": npc_id,
        "name": name,
        "age": 30,
        "gender": "female",
        "role": "test",
        "current_location_id": "loc_test",
        "personality": {
            "openness": 0.5,
            "conscientiousness": 0.5,
            "extraversion": 0.5,
            "agreeableness": 0.5,
            "neuroticism": 0.5,
            "honesty": 0.5,
            "courage": 0.5,
            "greed": 0.5,
            "loyalty": 0.5,
            "pride": 0.5,
        },
        "background": "bg",
    }


def test_symmetric_relationships_pass() -> None:
    a = NPC.model_validate(
        _minimal_npc_payload("npc_a", "A")
        | {
            "relationships": {
                "npc_b": {
                    "other_id": "npc_b",
                    "affection": 0.1,
                    "trust": 0.1,
                    "familiarity": 0.1,
                    "relationship_type": "朋友",
                    "relationship_label": "friend",
                }
            }
        }
    )
    b = NPC.model_validate(
        _minimal_npc_payload("npc_b", "B")
        | {
            "relationships": {
                "npc_a": {
                    "other_id": "npc_a",
                    "affection": 0.2,
                    "trust": 0.2,
                    "familiarity": 0.2,
                    "relationship_type": "朋友",
                    "relationship_label": "friend",
                }
            }
        }
    )
    # Numbers differ between sides, but symmetry only requires the edge to exist.
    check_relationship_symmetry([a, b])  # must not raise


def test_one_sided_relationship_fails() -> None:
    a = NPC.model_validate(
        _minimal_npc_payload("npc_a", "A")
        | {
            "relationships": {
                "npc_b": {
                    "other_id": "npc_b",
                    "affection": 0.1,
                    "trust": 0.1,
                    "familiarity": 0.1,
                    "relationship_type": "朋友",
                    "relationship_label": "friend",
                }
            }
        }
    )
    b = NPC.model_validate(_minimal_npc_payload("npc_b", "B"))  # B does not name A
    with pytest.raises(RelationshipSymmetryError) as exc:
        check_relationship_symmetry([a, b])
    assert "npc_a -> npc_b" in str(exc.value)
    assert "reverse edge" in str(exc.value)


def test_missing_other_side_is_tolerated() -> None:
    """If B isn't in the loaded set yet, A->B with no mirror is allowed."""
    a = NPC.model_validate(
        _minimal_npc_payload("npc_a", "A")
        | {
            "relationships": {
                "npc_b": {
                    "other_id": "npc_b",
                    "affection": 0.1,
                    "trust": 0.1,
                    "familiarity": 0.1,
                    "relationship_type": "朋友",
                    "relationship_label": "friend",
                }
            }
        }
    )
    check_relationship_symmetry([a])  # npc_b is not loaded, tolerated


def test_yaml_extra_field_rejected(tmp_path: Path) -> None:
    """extra='forbid' on NPC catches yaml schema drift."""
    bogus = tmp_path / "bogus.yaml"
    payload = _minimal_npc_payload("npc_bogus", "Bogus") | {"completely_made_up_field": 42}
    bogus.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_npc_yaml(bogus)
