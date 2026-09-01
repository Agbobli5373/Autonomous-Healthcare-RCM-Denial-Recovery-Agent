from __future__ import annotations

from datetime import date

from rcm_agent.domain import Authorization

AUTH = Authorization(
    authorization_number="AUTH-88213",
    valid_from=date(2026, 1, 1),
    valid_to=date(2026, 12, 31),
    covered_procedure_codes=("E1390", "J1745"),
)


def test_an_authorization_covers_a_service_inside_its_dates() -> None:
    assert AUTH.covers("E1390", date(2026, 3, 14))


def test_the_boundaries_are_inclusive() -> None:
    """A payer's validity range includes both ends; an off-by-one here loses an appeal."""
    assert AUTH.covers("E1390", date(2026, 1, 1))
    assert AUTH.covers("E1390", date(2026, 12, 31))


def test_a_service_before_the_range_is_not_covered() -> None:
    assert not AUTH.covers("E1390", date(2025, 12, 31))


def test_a_service_after_the_range_is_not_covered() -> None:
    assert not AUTH.covers("E1390", date(2027, 1, 1))


def test_a_procedure_outside_the_covered_scope_is_not_covered() -> None:
    assert not AUTH.covers("A4253", date(2026, 3, 14))


def test_an_authorization_with_no_listed_procedures_covers_any() -> None:
    """An unscoped authorization constrains dates only."""
    unscoped = Authorization("AUTH-1", date(2026, 1, 1), date(2026, 12, 31))

    assert unscoped.covers("A4253", date(2026, 3, 14))
    assert not unscoped.covers("A4253", date(2027, 1, 1))
