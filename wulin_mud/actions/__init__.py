"""Action layer.

Importing this package registers every concrete Action implementation
into ACTION_REGISTRY, so that `execute_action(action_name=..., ...)`
can resolve them by name.
"""

from wulin_mud.actions.base import (
    ACTION_REGISTRY,
    ActionResult,
    ActionType,
    CallerType,
    SideEffectManifest,
    ValidationResult,
    WitnessesRule,
    register_action,
)
from wulin_mud.actions.executor import (
    ActionCallerNotPermitted,
    ActionNotFound,
    execute_action,
)

# Side-effect imports: each module registers its Action into ACTION_REGISTRY.
from wulin_mud.actions import buy_item, greet, move_to, offend_npc  # noqa: F401

__all__ = [
    "ACTION_REGISTRY",
    "ActionCallerNotPermitted",
    "ActionNotFound",
    "ActionResult",
    "ActionType",
    "CallerType",
    "SideEffectManifest",
    "ValidationResult",
    "WitnessesRule",
    "execute_action",
    "register_action",
]
