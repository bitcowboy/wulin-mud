"""Prompt templates.

Templates live in their own subpackage so that:

- All prompts are in one searchable place (vs sprinkled in business logic).
- Renaming the LLM provider or changing call sites doesn't churn the
  templates themselves.
- Each prompt is a pure function: structured inputs → ``(system, user)``
  strings. No I/O. Easy to test by string assertion.
"""

from wulin_mud.llm.prompts.interpretation import build_interpretation_prompt

__all__ = ["build_interpretation_prompt"]
