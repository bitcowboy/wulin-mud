"""Action layer.

Importing this package registers every concrete Action implementation
into ACTION_REGISTRY, so that `execute_action(action_name=..., ...)`
can resolve them by name.
"""

# Side-effect imports: each module registers its Action into ACTION_REGISTRY.
from wulin_mud.actions import (  # noqa: F401
    buy_item,
    decay_memories,
    drift_mood,
    greet,
    move_to,
    offend_npc,
    talk,
)
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
