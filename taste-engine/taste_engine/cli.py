"""The ``taste`` command line: the only entry point to the pipeline."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from taste_engine import manifest
from taste_engine.schemas import Cohort
from taste_engine.settings import get_settings

log = logging.getLogger("taste")


def _cmd_manifest_import(args: argparse.Namespace) -> int:
    settings = get_settings()
    target = settings.manifest_path
    if target.exists() and not args.force:
        log.error("%s already exists; pass --force to replace it", target)
        return 1
    list_path = Path(args.list_path)
    urls = manifest.urls_from_text(list_path.read_text(encoding="utf-8"))
    entries = manifest.entries_from_urls(urls, Cohort(args.cohort), source=list_path.name)
    manifest.write_manifest(entries, target)
    log.info("wrote %d sites to %s", len(entries), target)
    return 0


def _cmd_manifest_show(args: argparse.Namespace) -> int:
    entries = manifest.read_manifest(get_settings().manifest_path)
    cohort = Cohort(args.cohort) if args.cohort else None
    chosen = manifest.select(entries, cohort=cohort)
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry.cohort] = counts.get(entry.cohort, 0) + 1
    for entry in chosen[: args.limit]:
        print(f"{entry.id:>5}  {entry.cohort:<9}  {entry.url}")
    print("total:", ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="taste")
    parser.add_argument("-v", "--verbose", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)

    manifest_cmd = commands.add_parser("manifest", help="manage the site manifest")
    manifest_sub = manifest_cmd.add_subparsers(dest="action", required=True)

    imp = manifest_sub.add_parser("import-list", help="create the manifest from a URL list")
    imp.add_argument("list_path")
    imp.add_argument("--cohort", default=Cohort.AWARD.value, choices=[c.value for c in Cohort])
    imp.add_argument("--force", action="store_true")
    imp.set_defaults(func=_cmd_manifest_import)

    show = manifest_sub.add_parser("show", help="list manifest entries")
    show.add_argument("--cohort", choices=[c.value for c in Cohort])
    show.add_argument("--limit", type=int, default=20)
    show.set_defaults(func=_cmd_manifest_show)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return args.func(args)
