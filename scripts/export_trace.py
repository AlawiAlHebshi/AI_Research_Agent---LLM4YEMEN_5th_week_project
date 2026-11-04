"""Validate and export a completed genuine CLI trace without overwriting evidence."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tracing import TraceError, export_trace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("label", choices=["success_1", "near_failure_recovery", "explicit_failure"])
    args = parser.parse_args()
    try:
        print(export_trace(args.path, args.label))
        return 0
    except (TraceError, OSError, ValueError):
        print("Export refused: unsuitable, invalid, offline or already-existing evidence.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
