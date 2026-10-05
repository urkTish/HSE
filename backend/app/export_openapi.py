"""Write the OpenAPI contract to docs/contracts/openapi.yaml.

Usage: ``uv run python -m app.export_openapi [--check]``. ``--check`` exits 1 if the committed
file is stale (used in CI).
"""

import sys
from pathlib import Path
from typing import Any

import yaml

from app.main import create_app

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "openapi.yaml"


def render() -> str:
    spec: dict[str, Any] = create_app().openapi()
    return yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=100)


def main(argv: list[str]) -> int:
    content = render()
    if "--check" in argv:
        current = CONTRACT_PATH.read_text(encoding="utf-8") if CONTRACT_PATH.exists() else ""
        if current != content:
            print(f"{CONTRACT_PATH} is stale; run `uv run python -m app.export_openapi`.")
            return 1
        print("Contract is up to date.")
        return 0
    CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONTRACT_PATH.write_text(content, encoding="utf-8")
    print(f"Wrote {CONTRACT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
