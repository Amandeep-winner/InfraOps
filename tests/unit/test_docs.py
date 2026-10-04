"""Documentation link integrity and markdown reference verification tests."""

import re
from pathlib import Path


def _slugify(text: str) -> str:
    """Convert heading text to GitHub-compatible markdown anchor slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


def _extract_headings(content: str) -> set[str]:
    """Extract all markdown heading slugs from document content."""
    headings = set()
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("#"):
            heading_text = line.lstrip("#").strip()
            slug = _slugify(heading_text)
            if slug:
                headings.add(slug)
    return headings


def test_markdown_documentation_links():
    """Verify all relative file references and anchor links in docs/ and README.md resolve."""
    root_dir = Path(__file__).resolve().parents[2]
    md_files = list((root_dir / "docs").glob("*.md"))
    readme = root_dir / "README.md"
    if readme.is_file():
        md_files.append(readme)

    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    broken_links = []

    for md_path in md_files:
        content = md_path.read_text(encoding="utf-8")
        current_headings = _extract_headings(content)

        for match in link_pattern.finditer(content):
            target = match.group(2).strip()

            # Skip external URLs, mailto, or image files
            if (
                target.startswith("http://")
                or target.startswith("https://")
                or target.startswith("mailto:")
            ):
                continue

            # In-page anchor: #anchor
            if target.startswith("#"):
                anchor = target.lstrip("#")
                if anchor not in current_headings:
                    broken_links.append(f"{md_path.name}: anchor '#{anchor}' not found")
                continue

            # Relative file path (with optional anchor)
            if "#" in target:
                rel_file, anchor = target.split("#", 1)
            else:
                rel_file, anchor = target, None

            # Resolve relative file target from current markdown file location
            target_path = (md_path.parent / rel_file).resolve()
            if not target_path.exists():
                # Try relative to repo root
                alt_path = (root_dir / rel_file).resolve()
                if not alt_path.exists():
                    broken_links.append(f"{md_path.name}: target file '{rel_file}' does not exist")
                    continue
                target_path = alt_path

            # If anchor is present, verify target heading exists in target document
            if anchor and target_path.suffix == ".md":
                target_content = target_path.read_text(encoding="utf-8")
                target_headings = _extract_headings(target_content)
                if anchor not in target_headings:
                    broken_links.append(
                        f"{md_path.name}: anchor '#{anchor}' not found in {target_path.name}"
                    )

    assert not broken_links, "Broken markdown links detected:\n" + "\n".join(broken_links)
