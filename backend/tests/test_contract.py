"""The committed OpenAPI contract must match the code."""

from app.core.config import CONTRACT_VERSION
from app.export_openapi import CONTRACT_PATH, render
from app.main import create_app


def test_contract_is_up_to_date() -> None:
    assert CONTRACT_PATH.read_text(encoding="utf-8") == render(), (
        "docs/contracts/openapi.yaml is stale: run `uv run python -m app.export_openapi`"
    )


def test_contract_version() -> None:
    assert f"version: {CONTRACT_VERSION}" in render()


def test_no_password_hash_in_contract() -> None:
    # AC35: password_hash is never part of any schema.
    schemas = create_app().openapi()["components"]["schemas"]
    for name, schema in schemas.items():
        assert "password_hash" not in schema.get("properties", {}), name
