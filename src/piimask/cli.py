"""Command-line interface: piimask scan | mask | restore."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .core import KINDS, find_pii, mask, restore


def _read(parser: argparse.ArgumentParser, path: str | None) -> str:
    if path is None or path == "-":
        return sys.stdin.read()
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        parser.error(f"cannot read {path!r}: {exc}")


def _kinds(parser: argparse.ArgumentParser, value: str | None) -> list[str] | None:
    if value is None:
        return None
    kinds = [k.strip().upper() for k in value.split(",") if k.strip()]
    unknown = sorted(set(kinds) - set(KINDS))
    if unknown:
        parser.error(f"unknown kinds {unknown}; choose from {', '.join(KINDS)}")
    return kinds


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="piimask", description="Mask UK personal data before sending text to an LLM, then restore it."
    )
    parser.add_argument("--version", action="version", version=f"piimask {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    kinds_help = f"Comma-separated kinds to look for (default: all of {', '.join(KINDS)})"

    scan = sub.add_parser("scan", help="Count personal data without printing it; exit 1 if any is found")
    scan.add_argument("path", nargs="?", help="Text file (default: stdin)")
    scan.add_argument("--kinds", help=kinds_help)

    m = sub.add_parser("mask", help="Replace personal data with placeholders such as <EMAIL_1>")
    m.add_argument("path", nargs="?", help="Text file (default: stdin)")
    m.add_argument("--kinds", help=kinds_help)
    m.add_argument("--mapping-out", help="Write the placeholder mapping (secret!) to this JSON file")
    m.add_argument("--json", action="store_true", help="Print JSON with text, mapping and counts")

    r = sub.add_parser("restore", help="Put original values back using a mapping file")
    r.add_argument("path", nargs="?", help="Text file (default: stdin)")
    r.add_argument("--mapping", required=True, help="JSON file written by `mask --mapping-out`")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    text = _read(parser, args.path)

    if args.command == "scan":
        matches = find_pii(text, _kinds(parser, args.kinds))
        counts: dict[str, int] = {}
        for match in matches:
            counts[match.kind] = counts.get(match.kind, 0) + 1
        print(json.dumps({"found": len(matches), "counts": counts}))
        return 1 if matches else 0

    if args.command == "mask":
        result = mask(text, _kinds(parser, args.kinds))
        if args.mapping_out:
            Path(args.mapping_out).write_text(json.dumps(result.mapping, indent=2, ensure_ascii=False) + "\n",
                                              encoding="utf-8")
        if args.json:
            print(json.dumps({"text": result.text, "mapping": result.mapping, "counts": result.counts()},
                             indent=2, ensure_ascii=False))
        else:
            sys.stdout.write(result.text)
            if result.mapping and not args.mapping_out:
                print("piimask: mapping not saved; use --mapping-out to restore later", file=sys.stderr)
        return 0

    try:
        mapping = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"cannot read mapping {args.mapping!r}: {exc}")
    if not isinstance(mapping, dict):
        parser.error("mapping file must contain a JSON object")
    sys.stdout.write(restore(text, mapping))
    return 0


if __name__ == "__main__":
    sys.exit(main())
