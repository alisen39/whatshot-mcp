from __future__ import annotations

import pytest

from whatshot_mcp.contracts.v1 import (
    BOARD_KEY_VERSION,
    SUPPORTED_BOARD_DIMENSIONS,
    BoardIdentityError,
    canonical_board_key,
)


def test_board_key_v1_has_fixed_identity_without_dimensions() -> None:
    assert BOARD_KEY_VERSION == 1
    assert (
        canonical_board_key(
            path_type="hot",
            params={},
            declared_dimensions=(),
        )
        == "hot"
    )


def test_board_key_v1_orders_type_first_then_dimension_names() -> None:
    assert (
        canonical_board_key(
            path_type="ranking",
            params={"range": "week", "game": "genshin"},
            declared_dimensions={"range", "type", "game"},
        )
        == "type=ranking&game=genshin&range=week"
    )


def test_board_key_v1_uses_rfc3986_utf8_encoding() -> None:
    assert canonical_board_key(
        path_type="weather",
        params={
            "province": "北京市 海淀/区",
            "month": "2026-08",
            "day": "2026-08-13",
        },
        declared_dimensions={"type", "province", "month", "day"},
    ) == (
        "type=weather&day=2026-08-13&month=2026-08&"
        "province=%E5%8C%97%E4%BA%AC%E5%B8%82%20%E6%B5%B7%E6%B7%80%2F%E5%8C%BA"
    )


@pytest.mark.parametrize(
    ("params", "declared", "message"),
    [
        ({"limit": "10"}, {"limit"}, "unsupported declared"),
        ({"sort": "new"}, {"type"}, "not declared"),
        ({"type": "new"}, {"type"}, "only as path_type"),
        ({"range": ""}, {"range"}, "non-empty string value"),
        ({"": "value"}, {"range"}, "non-empty strings"),
    ],
)
def test_board_key_v1_rejects_invalid_dimensions(
    params: dict[str, str],
    declared: set[str],
    message: str,
) -> None:
    with pytest.raises(BoardIdentityError, match=message):
        canonical_board_key(
            path_type="hot",
            params=params,
            declared_dimensions=declared,
        )


def test_contract_dimensions_are_frozen() -> None:
    assert SUPPORTED_BOARD_DIMENSIONS == {
        "type",
        "game",
        "range",
        "sort",
        "province",
        "day",
        "month",
    }
