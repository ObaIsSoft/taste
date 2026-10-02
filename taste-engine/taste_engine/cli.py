"""The ``taste`` command line: the only entry point to the pipeline."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from taste_engine import manifest
from taste_engine.capture import runner, site
from taste_engine.schemas import CaptureStatus, Cohort, Variant
from taste_engine.settings import get_settings

log = logging.getLogger("taste")


def parse_ids(spec: str) -> list[int]:
    """Parse "1,4,10-12" into [1, 4, 10, 11, 12]."""
    ids: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            first, last = (int(x) for x in part.split("-", 1))
            ids.extend(range(first, last + 1))
        else:
            ids.append(int(part))
    return ids


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


def _cmd_capture(args: argparse.Namespace) -> int:
    settings = get_settings()
    entries = manifest.select(
        manifest.read_manifest(settings.manifest_path),
        ids=parse_ids(args.ids) if args.ids else None,
        cohort=Cohort(args.cohort) if args.cohort else None,
        limit=args.limit,
    )
    variants = [Variant(v) for v in args.variants.split(",")]
    jobs = runner.plan(entries, variants, settings, force=args.force)
    log.info(
        "%d captures to run, %d already done", len(jobs), len(entries) * len(variants) - len(jobs)
    )
    counts = runner.run(jobs, settings)
    log.info(
        "finished: %d ok, %d failed QA, %d failed",
        counts["ok"],
        counts["qa_failed"],
        counts["failed"],
    )
    return 0 if counts["failed"] == 0 else 2


def _cmd_capture_one(args: argparse.Namespace) -> int:
    settings = get_settings()
    [entry] = manifest.select(manifest.read_manifest(settings.manifest_path), ids=[args.site_id])
    record = site.capture_site(entry, Variant(args.variant), settings)
    return 0 if record.status == CaptureStatus.OK else 2


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

    capture = commands.add_parser("capture", help="capture sites (resumable, parallel)")
    capture.add_argument("--ids", help='site ids, e.g. "1-14,20"')
    capture.add_argument("--cohort", choices=[c.value for c in Cohort])
    capture.add_argument("--limit", type=int)
    capture.add_argument(
        "--variants",
        default=Variant.ORIGINAL.value,
        help="comma-separated: " + ",".join(v.value for v in Variant),
    )
    capture.add_argument("--force", action="store_true", help="re-capture finished sites")
    capture.set_defaults(func=_cmd_capture)

    one = commands.add_parser("capture-one", help="capture one site in this process")
    one.add_argument("--site-id", type=int, required=True)
    one.add_argument(
        "--variant", default=Variant.ORIGINAL.value, choices=[v.value for v in Variant]
    )
    one.set_defaults(func=_cmd_capture_one)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return args.func(args)
