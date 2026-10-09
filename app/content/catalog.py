"""Discover and validate content packs available in the repository."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.content.pack import ContentPack, load_content_pack

CONTENT_ROOT = Path(__file__).resolve().parents[2] / "content"


@dataclass(frozen=True)
class PackIssue:
    directory: str
    message: str


@dataclass(frozen=True)
class ContentPackEntry:
    path: Path
    pack: ContentPack


def scan_content_packs(
    root: Path | None = None,
    *,
    include_examples: bool = False,
) -> tuple[list[ContentPackEntry], list[PackIssue]]:
    """Return valid pack files and per-folder validation errors.

    Directories without a ``content.json`` are data folders, not pack candidates.
    """
    root = root or CONTENT_ROOT
    entries: list[ContentPackEntry] = []
    issues: list[PackIssue] = []
    roots = [(root, "")]
    if include_examples:
        roots.append((root / "examples", "examples/"))
    for pack_root, prefix in roots:
        if not pack_root.is_dir():
            continue
        for directory in sorted(pack_root.iterdir(), key=lambda item: item.name.casefold()):
            if not directory.is_dir():
                continue
            path = directory / "content.json"
            if not path.is_file():
                continue
            try:
                pack = load_content_pack(path)
            except (OSError, ValueError) as exc:
                issues.append(PackIssue(directory=f"{prefix}{directory.name}", message=str(exc)))
                continue
            entries.append(ContentPackEntry(path=path, pack=pack))
    return entries, issues
