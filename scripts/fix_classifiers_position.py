"""Fix-up: move classifiers = [...] back under [project] in every pyproject.

The earlier normaliser inserted the block AFTER existing [project.entry-points.*]
sections in a few files, which TOML reads as belonging to that entry-points table.
We move it to be the last key inside [project] (i.e. before any [project.X] section).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CLASSIFIERS_RE = re.compile(r"\nclassifiers = \[[^\]]*\]\n", re.DOTALL)


def fix(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    matches = list(CLASSIFIERS_RE.finditer(text))
    if not matches:
        return False
    # Take the LAST classifiers block (the inserted one), strip it, then re-insert
    # at the right spot.
    block = matches[-1].group(0)
    text = text[: matches[-1].start()] + text[matches[-1].end() :]

    # Re-insert immediately before the first [project.X] subsection (urls / scripts /
    # entry-points etc) or, failing that, before [tool.* / build-system].
    insert_marker = re.search(r"\n\[project\.|\n\[tool\.|\n\[build-system\]", text)
    if insert_marker is None:
        return False
    idx = insert_marker.start()
    new_text = text[:idx] + block + text[idx:]
    if new_text == path.read_text(encoding="utf-8"):
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def main() -> None:
    targets: list[Path] = [
        ROOT / "packages/aglet/pyproject.toml",
        ROOT / "packages/aglet-cli/pyproject.toml",
        ROOT / "packages/aglet-server/pyproject.toml",
        ROOT / "packages/aglet-eval/pyproject.toml",
        *sorted((ROOT / "packages/aglet-builtin").glob("*/pyproject.toml")),
    ]
    fixed = 0
    for path in targets:
        if fix(path):
            print(f"fixed {path.relative_to(ROOT)}")
            fixed += 1
    print(f"\n{fixed} files fixed.")


if __name__ == "__main__":
    main()
