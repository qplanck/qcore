"""Validate Phase 0 documentation structure and local Markdown links."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "node_modules"}
LINK_RE = re.compile(r"!?\[[^\]]*\]\((?P<target><[^>]+>|[^)\s]+)(?:\s+[^)]*)?\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
MERMAID_RE = re.compile(r"^```mermaid\s*\n(?P<body>.*?)^```\s*$", re.MULTILINE | re.DOTALL)

MANDATORY_FILES = (
    "docs/executive-summary.md",
    "docs/research/source-register.md",
    "docs/research/ecosystem-audit.md",
    "docs/research/qbraid-analysis.md",
    "docs/research/competitive-matrix.md",
    "docs/research/current-alpha-audit.md",
    "docs/strategy/qcore-positioning.md",
    "docs/architecture/qcore-overview.md",
    "docs/architecture/ir-strategy.md",
    "docs/architecture/compiler-pipeline.md",
    "docs/architecture/runtime-and-backends.md",
    "docs/architecture/plugin-system.md",
    "docs/architecture/ai-agent-architecture.md",
    "docs/architecture/qplanck-labs.md",
    "docs/roadmap/qcore-roadmap.md",
    "docs/roadmap/mvp-definition.md",
    "docs/roadmap/implementation-backlog.md",
    "docs/security/threat-model.md",
    "docs/governance/open-source-governance.md",
    "docs/reviews/phase-0-review.md",
    "rfcs/0001-qcore-charter.md",
    "rfcs/0002-language-and-repository-strategy.md",
    "rfcs/0003-intermediate-representation.md",
    "rfcs/0004-backend-interface.md",
)


def markdown_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if not EXCLUDED_PARTS.intersection(path.relative_to(ROOT).parts)
    )


def github_slug(text: str) -> str:
    text = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("`", "").replace("*", "").replace("_", "_")
    text = re.sub(r"[^\w\- ]", "", text.lower())
    return re.sub(r"-+", "-", text.replace(" ", "-")).strip("-")


def anchors_for(path: Path) -> set[str]:
    anchors: set[str] = set()
    seen: defaultdict[str, int] = defaultdict(int)
    in_fence = False
    fence_marker = ""

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
            continue
        if in_fence:
            continue
        match = HEADING_RE.match(line)
        if match is None:
            continue
        base = github_slug(match.group(2))
        suffix = seen[base]
        seen[base] += 1
        anchors.add(base if suffix == 0 else f"{base}-{suffix}")
    return anchors


def iter_link_targets(path: Path) -> list[tuple[int, str]]:
    targets: list[tuple[int, str]] = []
    in_fence = False
    fence_marker = ""
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
            continue
        if in_fence:
            continue
        for match in LINK_RE.finditer(line):
            target = match.group("target").strip("<>")
            targets.append((line_number, target))
    return targets


def validate_structure(errors: list[str]) -> None:
    for relative in MANDATORY_FILES:
        if not (ROOT / relative).is_file():
            errors.append(f"missing mandatory document: {relative}")

    for relative in MANDATORY_FILES[-4:]:
        path = ROOT / relative
        if path.is_file() and "Status: **Proposed**" not in path.read_text(encoding="utf-8"):
            errors.append(f"RFC must remain Proposed pending review: {relative}")


def validate_links(files: list[Path], errors: list[str]) -> None:
    anchor_cache: dict[Path, set[str]] = {}
    for source in files:
        for line_number, target in iter_link_targets(source):
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or target.startswith(("mailto:", "data:")):
                continue

            linked = source if not parsed.path else (source.parent / unquote(parsed.path)).resolve()
            try:
                linked.relative_to(ROOT)
            except ValueError:
                errors.append(
                    f"{source.relative_to(ROOT)}:{line_number}: local link escapes repository: {target}"
                )
                continue

            if not linked.exists():
                errors.append(
                    f"{source.relative_to(ROOT)}:{line_number}: missing local target: {target}"
                )
                continue

            if parsed.fragment and linked.is_file() and linked.suffix.lower() == ".md":
                anchors = anchor_cache.setdefault(linked, anchors_for(linked))
                fragment = unquote(parsed.fragment).lower()
                if fragment not in anchors:
                    errors.append(
                        f"{source.relative_to(ROOT)}:{line_number}: missing anchor "
                        f"#{fragment} in {linked.relative_to(ROOT)}"
                    )


def extract_mermaid(files: list[Path], output: Path) -> int:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    count = 0
    for source in files:
        text = source.read_text(encoding="utf-8")
        for index, match in enumerate(MERMAID_RE.finditer(text), start=1):
            count += 1
            stem = "-".join(source.relative_to(ROOT).with_suffix("").parts)
            destination = output / f"{stem}-{index:02d}.mmd"
            destination.write_text(match.group("body").strip() + "\n", encoding="utf-8")
    return count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--extract-mermaid",
        type=Path,
        help="Replace this directory with individual Mermaid source files for rendering.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    files = markdown_files()
    errors: list[str] = []
    validate_structure(errors)
    validate_links(files, errors)

    diagram_count = 0
    if args.extract_mermaid is not None:
        diagram_count = extract_mermaid(files, args.extract_mermaid)
        if diagram_count == 0:
            errors.append("no Mermaid diagrams found")

    if errors:
        for error in errors:
            print(f"docs: error: {error}", file=sys.stderr)
        return 1

    print(f"docs: checked {len(files)} Markdown files and {diagram_count} Mermaid diagrams")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
