"""Module entry point. Allows ``python -m wulin_mud.eval``."""

from wulin_mud.eval.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
