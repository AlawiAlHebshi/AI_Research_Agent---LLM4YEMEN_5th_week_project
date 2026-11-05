"""Secure local launcher: process environment or masked terminal input, never .env."""

from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import warnings
from typing import Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]


def prepare_environment(environment: Mapping[str, str], *, interactive: bool,
                        prompt: Callable[[str], str]) -> dict[str, str]:
    """Pass credentials to the child environment only, never command arguments or files."""
    result = dict(environment)
    if not result.get("OPENAI_API_KEY"):
        if not interactive:
            raise ValueError("OpenAI API credential is missing; use an interactive terminal or configure the process environment.")
        credential = prompt("OpenAI API key (hidden; not saved): ").strip()
        if not credential or "\n" in credential or "\r" in credential:
            raise ValueError("A nonempty credential is required.")
        result["OPENAI_API_KEY"] = credential
    result["LANGSMITH_TRACING"] = "false"
    result["LANGCHAIN_TRACING_V2"] = "false"
    result["AI_RESEARCH_RUNTIME"] = "local"
    return result


def main(argv=None, *, run=None, prompt=None, environment=None, interactive=None) -> int:
    parser = argparse.ArgumentParser(description="Start the connected local Streamlit app without reading .env.")
    parser.add_argument("--port", type=int, default=8502)
    parser.add_argument("--check", action="store_true", help="Show credential presence booleans only; do not start research or a server.")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    environment = os.environ if environment is None else environment
    if args.check:
        print(json.dumps({"openai_key_present": bool(environment.get("OPENAI_API_KEY")),
                          "asta_key_present": bool(environment.get("ASTA_TOOL_KEY")), "port": args.port}))
        return 0
    try:
        with warnings.catch_warnings():
            # Fail closed rather than allowing getpass to fall back to echoed input.
            warnings.simplefilter("error", getpass.GetPassWarning)
            child_environment = prepare_environment(environment,
                interactive=sys.stdin.isatty() if interactive is None else interactive,
                prompt=prompt or getpass.getpass)
    except (ValueError, EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        print("Credential unavailable or entry cancelled. No server or API request was started.")
        return 2
    command = [sys.executable, "-B", "-m", "streamlit", "run", str(ROOT / "streamlit_app.py"),
               "--server.address", "127.0.0.1", "--server.port", str(args.port),
               "--server.headless", "true", "--server.fileWatcherType", "none", "--browser.gatherUsageStats", "false"]
    print(f"Starting the connected app at http://127.0.0.1:{args.port}/ (local operator only).")
    try:
        return (run or subprocess.run)(command, cwd=ROOT, env=child_environment).returncode
    except (OSError, KeyboardInterrupt):
        print("Local server stopped or could not start. No credential details were printed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
