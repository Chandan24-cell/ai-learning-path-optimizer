"""Import a validated subject pack with ``python -m app.content import PATH``."""

from __future__ import annotations

import argparse
import logging
import sys

from app.content.catalog import scan_content_packs
from app.content.pack import import_content_pack
from app.database import SessionLocal

_logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.content")
    subparsers = parser.add_subparsers(dest="command", required=True)
    importer = subparsers.add_parser("import", help="validate and import a content pack")
    importer.add_argument("path", help="directory containing content.json, or a JSON file")
    subparsers.add_parser("import-all", help="import every valid pack under content/")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.command == "import":
            try:
                result = import_content_pack(args.path, db)
            except (OSError, ValueError) as exc:
                db.rollback()
                print(f"Content import failed: {exc}", file=sys.stderr)
                return 2
            print(
                f"Imported {result['subject']}: {result['topics']} topics, "
                f"{result['resources']} resources, {result['questions']} questions."
            )
            return 0

        entries, issues = scan_content_packs(include_examples=True)
        failed = bool(issues)
        for issue in issues:
            _logger.error(
                "Content pack validation failed in %s: %s", issue.directory, issue.message
            )
        for entry in entries:
            try:
                result = import_content_pack(entry.path, db)
            except OSError, ValueError:
                db.rollback()
                _logger.exception("Content pack import failed in %s", entry.path.parent.name)
                failed = True
                continue
            print(
                f"Imported {result['subject']}: {result['topics']} topics, "
                f"{result['resources']} resources, {result['questions']} questions."
            )
        return 1 if failed else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
