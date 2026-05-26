"""Initialize the game world from seed YAML files.

Run with:
    python -m wulin_mud.scripts.seed_world

This script will be implemented in the first coding sprint. For now it
documents what the seeding process needs to do.
"""

# TODO (v0.1, Day 3-4):
#   1. Read all YAML files under wulin_mud/world/seed_data/
#   2. Validate against Ontology schema (pydantic models)
#   3. Cross-check relationship symmetry (if A relates to B, B must relate back)
#   4. Insert into SQLite database at $WULIN_DB_URL
#   5. Generate initial Memory objects for relationships flagged with
#      notable_memory_seed: true
#
# See docs/ontology.md and docs/npc-spec.md.


def main() -> None:
    raise NotImplementedError(
        "World seeding is not implemented yet. See docs/roadmap.md, " "v0.1 Day 3-4 milestone."
    )


if __name__ == "__main__":
    main()
