"""Entry point: the v3 screen by default, the ring course with --fly [bindings.xml]."""
from __future__ import annotations

import sys


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--fly" in argv:
        i = argv.index("--fly")
        path = argv[i + 1] if i + 1 < len(argv) else None
        from .app import main as fly
        fly(path)
        return 0
    from .webui import main as screen
    return screen()
