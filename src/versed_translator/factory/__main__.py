"""python -m versed_translator.factory {simulate,prepare,merge}"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m versed_translator.factory")
    parser.add_argument("cmd", choices=("simulate", "prepare", "merge"))
    args, rest = parser.parse_known_args(argv)
    if args.cmd == "simulate":
        from versed_translator.factory.simulate import main as sim_main

        return sim_main(rest)
    if args.cmd == "merge":
        from versed_translator.factory.merge import main as merge_main

        return merge_main(rest)
    from versed_translator.factory.prepare import main as prep_main

    return prep_main(rest)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
