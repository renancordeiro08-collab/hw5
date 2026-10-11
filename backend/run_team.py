"""Run the agent team from the command line.

    .venv/bin/python -m backend.run_team --reset --all     # fresh DB, work every open ticket
    .venv/bin/python -m backend.run_team --ticket 101      # one ticket
"""

import argparse
import asyncio
import json
import shutil

from .config import MODEL_NAME, ORIGINAL_DB, WORKING_DB


def reset_db() -> None:
    """Copy the untouched original over the working copy."""
    shutil.copyfile(ORIGINAL_DB, WORKING_DB)
    print(f"Reset {WORKING_DB.name} from {ORIGINAL_DB.name}.")


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--ticket", type=int, help="work one ticket")
    p.add_argument("--all", action="store_true", help="work every open ticket")
    p.add_argument("--reset", action="store_true", help="reset the working DB first")
    args = p.parse_args()
    if args.reset:
        reset_db()
    if not (args.ticket or args.all):
        return

    from .agents.team import run_board, run_ticket  # import after reset

    print(f"Model: {MODEL_NAME}")
    decisions = await run_board() if args.all else [await run_ticket(args.ticket)]
    for d in decisions:
        print(json.dumps(d.model_dump(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
