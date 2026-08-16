from __future__ import annotations

import json
from pathlib import Path

from whatshot_mcp.contracts.v1 import (
    canonical_board_key,
    normalize_search_text,
)

FIXTURES = Path(__file__).parents[1] / "contracts" / "fixtures" / "v1"


def test_board_key_release_vectors() -> None:
    payload = json.loads((FIXTURES / "board-key-vectors.json").read_text())

    assert payload["version"] == 1
    for vector in payload["vectors"]:
        assert (
            canonical_board_key(
                path_type=vector["pathType"],
                params=vector["params"],
                declared_dimensions=vector["declaredDimensions"],
            )
            == vector["boardKey"]
        )


def test_search_normalization_release_vectors() -> None:
    payload = json.loads((FIXTURES / "search-normalization-vectors.json").read_text())

    assert payload["version"] == 1
    for vector in payload["vectors"]:
        assert normalize_search_text(vector["input"]) == vector["normalized"]
