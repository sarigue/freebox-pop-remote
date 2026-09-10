"""Nuitka entry point used by native platform builds."""

from freebox_pop_remote.main import main

if __name__ == "__main__":
    raise SystemExit(main())
