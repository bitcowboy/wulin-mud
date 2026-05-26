"""Action base class and registry.

See docs/action-types.md for the full specification.

Implementations live in sibling modules under this package, e.g.
    wulin_mud/actions/buy_item.py    -> BuyItem(ActionType)
    wulin_mud/actions/talk.py        -> Talk(ActionType)
    ...

This file only defines the abstract base and the registry pattern.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from wulin_mud.world.state import WorldState


class CallerType(str, Enum):
    """Who is permitted to invoke an action."""

    PLAYER = "player"
    NPC = "npc"
    SYSTEM = "system"


@dataclass
class ValidationResult:
    """Outcome of an action's pre-condition check."""

    ok: bool
    reason: str | None = None


@dataclass
class SideEffectManifest:
    """Static declaration of what an action could affect.

    Used by the engine to:
    - Compute the witness set (who gets a Memory)
    - Trigger downstream propagation rules
    - Detect conflicts between concurrent actions
    """

    mutates_fields: list[str] = field(default_factory=list)
    witnesses_rule: str = "SAME_LOCATION"
    generates_rumor: bool = False
    rumor_spice: float = 0.0
    triggers_delayed: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ActionResult:
    """Outcome of executing an action."""

    succeeded: bool
    action_record_id: str
    side_effects_applied: list[dict[str, Any]] = field(default_factory=list)
    memories_generated: list[str] = field(default_factory=list)
    narrative_hint: str | None = None  # passed to the LLM rendering layer


class ActionType(ABC):
    """Base class for all action types.

    Engineering red line: the LLM never bypasses an ActionType to write
    world state. All mutations must flow through .execute().
    See docs/architecture.md section 3.
    """

    name: str
    description: str
    callable_by: set[CallerType]

    @abstractmethod
    def validate(
        self,
        params: dict[str, Any],
        world: WorldState,
        actor_id: str,
    ) -> ValidationResult:
        """Check pre-conditions. Return reason if invalid."""

    @abstractmethod
    def declare_side_effects(self, params: dict[str, Any]) -> SideEffectManifest:
        """Statically declare what this action could affect."""

    @abstractmethod
    async def execute(
        self,
        params: dict[str, Any],
        world: WorldState,
        actor_id: str,
    ) -> ActionResult:
        """Apply side effects, generate memories, return result."""


# Populated as concrete actions register themselves.
ACTION_REGISTRY: dict[str, ActionType] = {}


def register_action(action: ActionType) -> ActionType:
    """Decorator/helper to register an action instance."""
    if action.name in ACTION_REGISTRY:
        raise ValueError(f"Action {action.name!r} already registered")
    ACTION_REGISTRY[action.name] = action
    return action
