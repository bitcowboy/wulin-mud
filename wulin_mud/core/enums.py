"""Project-wide enumerations.

Per docs/ontology.md section 4: "能用枚举就不用自由文本".
All string-typed categorical fields across the ontology and action layers
draw their values from these enums, not from ad-hoc string literals.
"""

from __future__ import annotations

from enum import Enum


class CallerType(str, Enum):
    """Who is permitted to invoke an action.

    Re-exported from wulin_mud.actions.base for backwards compatibility.
    """

    PLAYER = "player"
    NPC = "npc"
    SYSTEM = "system"


class Gender(str, Enum):
    """NPC biological gender (used only for narrative grounding)."""

    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class EventType(str, Enum):
    """Classification of what happened in an event/memory.

    Kept deliberately small in v0.1. New values are added as new Actions
    are introduced (see docs/action-types.md).
    """

    MET = "met"
    TALKED = "talked"
    HAGGLED = "haggled"
    HELPED = "helped"
    HARMED = "harmed"
    WITNESSED = "witnessed"
    HEARD_RUMOR = "heard_rumor"
    BOUGHT = "bought"
    SOLD = "sold"
    GIFTED = "gifted"
    STOLE = "stole"
    OFFENDED = "offended"
    THREATENED = "threatened"
    SAVED_LIFE = "saved_life"
    BETRAYED = "betrayed"
    LIED_TO = "lied_to"
    OBSERVED = "observed"


class LocationType(str, Enum):
    """Types of in-world locations.

    Values cover the v0.1 Qinghe-town locations (see docs/world-setting.md).
    """

    PIER = "pier"
    INN = "inn"
    PHARMACY = "pharmacy"
    TEAHOUSE = "teahouse"
    ESCORT_AGENCY = "escort_agency"
    SMITHY = "smithy"
    PAWNSHOP = "pawnshop"
    RESIDENCE = "residence"
    MAGISTRATE = "magistrate"
    GAMBLING_DEN = "gambling_den"
    SHRINE = "shrine"
    STREET = "street"
    OTHER = "other"


class ItemType(str, Enum):
    """Types of items players or NPCs can own."""

    MEDICINE = "medicine"
    FOOD = "food"
    WEAPON = "weapon"
    LETTER = "letter"
    MONEY_POUCH = "money_pouch"
    CLOTHING = "clothing"
    BOOK = "book"
    TOOL = "tool"
    OTHER = "other"


class RelationshipType(str, Enum):
    """Broad category of an NPC↔NPC relationship.

    Values are the Chinese labels used by the spec (docs/ontology.md §2.4)
    and the seed YAMLs. The narrative-specific phrasing lives in
    Relationship.relationship_label instead.
    """

    KIN = "亲属"
    FRIEND = "朋友"
    OLD_ACQUAINTANCE = "旧识"
    NEIGHBOR = "邻里"
    BUSINESS = "生意伙伴"
    EMPLOYMENT = "雇佣"
    NEMESIS = "宿敌"
    STRANGER = "陌生人"


class InitiatedBy(str, Enum):
    """Who/what initiated an action (ActionRecord.initiated_by)."""

    PLAYER_INPUT = "player_input"
    WORLD_TICK = "world_tick"
    LLM_DECISION = "llm_decision"


class WitnessesRule(str, Enum):
    """How an Action's witness set is computed.

    See docs/action-types.md §5.2.
    """

    SAME_LOCATION = "SAME_LOCATION"
    EXPLICIT = "EXPLICIT"
    FACTION_MEMBERS = "FACTION_MEMBERS"
    RELATED_TO_PARTICIPANT = "RELATED_TO_PARTICIPANT"
