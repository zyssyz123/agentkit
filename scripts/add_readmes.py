"""Generate a stub README.md for every publishable package and ensure pyproject
declares ``readme = "README.md"`` so PyPI renders a description page.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_URL = "https://github.com/zyssyz123/agentkit"


def _description_from(pyproject: Path) -> str:
    text = pyproject.read_text(encoding="utf-8")
    m = re.search(r'^description = "([^"]+)"', text, flags=re.MULTILINE)
    return m.group(1) if m else ""


def _name_from(pyproject: Path) -> str:
    text = pyproject.read_text(encoding="utf-8")
    m = re.search(r'^name = "([^"]+)"', text, flags=re.MULTILINE)
    return m.group(1) if m else ""


README_TEMPLATE = """\
# {name}

> {description}

Part of the [Aglet]({repo}) pluggable Agent runtime — a framework where every
Element (perception, memory, planner, tool, executor, safety, output, observability,
extensibility) **and** every Technique within an Element is a swappable plugin
distributed as its own PyPI package.

## Install

```bash
pip install {name}
```

This package registers itself with Aglet's `Registry` at import time via
Python entry points. Once installed, list it with:

```bash
aglet techniques        # if your installed version of aglet-cli is recent
```

## Usage

In your `agent.yaml`:

```yaml
elements:
  # Add the Element / technique block this package contributes.
```

See the [main repo's examples]({repo}/tree/main/examples) for full configurations.

## License

Apache-2.0
"""


def main() -> None:
    targets: list[Path] = [
        ROOT / "packages/aglet/pyproject.toml",
        ROOT / "packages/aglet-cli/pyproject.toml",
        ROOT / "packages/aglet-server/pyproject.toml",
        ROOT / "packages/aglet-eval/pyproject.toml",
        *sorted((ROOT / "packages/aglet-builtin").glob("*/pyproject.toml")),
    ]

    for pyproject in targets:
        readme_path = pyproject.parent / "README.md"
        name = _name_from(pyproject)
        if not readme_path.exists():
            description = _description_from(pyproject)
            readme_path.write_text(
                README_TEMPLATE.format(name=name, description=description, repo=REPO_URL),
                encoding="utf-8",
            )
            print(f"created README for {pyproject.parent.relative_to(ROOT)}")

        # Make sure pyproject declares readme = "README.md".
        text = pyproject.read_text(encoding="utf-8")
        if "readme = " not in text:
            text = text.replace(
                'license = "Apache-2.0"',
                'license = "Apache-2.0"\nreadme = "README.md"',
                1,
            )
            pyproject.write_text(text, encoding="utf-8")
            print(f"  added readme= to {pyproject.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
