"""One-shot helper: ensure every publishable package has consistent PyPI metadata.

Usage::

    python scripts/normalise_pyprojects.py
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOMEPAGE = "https://github.com/zyssyz123/agentkit"
ISSUES = "https://github.com/zyssyz123/agentkit/issues"
SOURCE = "https://github.com/zyssyz123/agentkit"
AUTHOR_BLOCK = 'authors = [{ name = "The Aglet Contributors" }]'
LICENSE_LINE = 'license = "Apache-2.0"'
PY_VERSION_LINE = 'requires-python = ">=3.11"'

CLASSIFIERS = """\
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: Apache Software License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Scientific/Engineering :: Artificial Intelligence",
]"""

URLS_BLOCK = f"""[project.urls]
Homepage = "{HOMEPAGE}"
Repository = "{SOURCE}"
Issues = "{ISSUES}"
"""

PUBLISHABLE = [
    "packages/aglet",
    "packages/aglet-cli",
    "packages/aglet-server",
    "packages/aglet-eval",
    *sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "packages/aglet-builtin").iterdir() if (p / "pyproject.toml").exists()),
]


def _ensure_classifiers(text: str) -> str:
    if "classifiers = [" in text:
        # Replace existing classifiers block.
        return re.sub(
            r"classifiers = \[[^\]]*\]",
            CLASSIFIERS,
            text,
            count=1,
            flags=re.DOTALL,
        )
    # Insert before [project.urls] or [tool.* ] or end of [project] block.
    insert_marker = re.search(r"\n\[project\.urls\]|\n\[tool\.", text)
    if insert_marker is None:
        return text + "\n" + CLASSIFIERS + "\n"
    idx = insert_marker.start()
    return text[:idx] + "\n" + CLASSIFIERS + "\n" + text[idx:]


def _ensure_urls(text: str) -> str:
    # Drop any existing [project.urls] block (single-section, end at next [section] or EOF).
    text = re.sub(
        r"\[project\.urls\][^\[]*",
        "",
        text,
        count=1,
    ).rstrip() + "\n"
    # Re-insert URLS_BLOCK before [tool.hatch... or [build-system or EOF.
    insert_marker = re.search(r"\n\[tool\.|\n\[build-system\]", text)
    if insert_marker is None:
        return text + "\n" + URLS_BLOCK
    idx = insert_marker.start()
    return text[:idx] + "\n" + URLS_BLOCK + text[idx:]


def _ensure_simple_lines(text: str) -> str:
    if "license = " not in text:
        text = text.replace("requires-python", LICENSE_LINE + "\n" + "requires-python", 1)
    if "authors = " not in text:
        text = text.replace("license = ", AUTHOR_BLOCK + "\n" + "license = ", 1)
    return text


def normalise(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    new = text
    new = _ensure_simple_lines(new)
    new = _ensure_classifiers(new)
    new = _ensure_urls(new)
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def main() -> None:
    changed = 0
    for rel in PUBLISHABLE:
        path = ROOT / rel / "pyproject.toml"
        if normalise(path):
            print(f"updated {rel}")
            changed += 1
    print(f"\n{changed} pyproject.toml files updated.")


if __name__ == "__main__":
    main()
