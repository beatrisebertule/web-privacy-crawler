"""
Tests for Q11's Referrer-Policy parsing.

Skipped-token tests also have a recognized token when they can.
"""

# Standard library imports
import importlib

# Third party imports
import pytest

# Import statement can't load a module name starting with a digit.
q11 = importlib.import_module("11_analysis")

ReferrerPolicy = q11.ReferrerPolicy
ReferrerPolicyHeader = q11.ReferrerPolicyHeader
parse_referrer_policy = q11.parse_referrer_policy

NO_REFERRER = ReferrerPolicy.NO_REFERRER
UNSAFE_URL = ReferrerPolicy.UNSAFE_URL
STRICT_ORIGIN_WHEN_CROSS_ORIGIN = ReferrerPolicy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN


# *******************************************
# Recognized tokens
# *******************************************


@pytest.mark.parametrize(
    ("token", "policy"),
    [
        ("no-referrer", ReferrerPolicy.NO_REFERRER),
        ("no-referrer-when-downgrade", ReferrerPolicy.NO_REFERRER_WHEN_DOWNGRADE),
        ("origin", ReferrerPolicy.ORIGIN),
        ("origin-when-cross-origin", ReferrerPolicy.ORIGIN_WHEN_CROSS_ORIGIN),
        ("same-origin", ReferrerPolicy.SAME_ORIGIN),
        ("strict-origin", ReferrerPolicy.STRICT_ORIGIN),
        ("strict-origin-when-cross-origin", ReferrerPolicy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN),
        ("unsafe-url", ReferrerPolicy.UNSAFE_URL),
    ],
)
def test_each_token_alone(token: str, policy: ReferrerPolicy) -> None:
    assert parse_referrer_policy([token]) == ReferrerPolicyHeader(policy, frozenset({policy}))


def test_last_token_wins_over_fallback() -> None:
    header = parse_referrer_policy(["no-referrer, strict-origin-when-cross-origin"])
    assert header.effective is STRICT_ORIGIN_WHEN_CROSS_ORIGIN
    assert header.listed == frozenset({NO_REFERRER, STRICT_ORIGIN_WHEN_CROSS_ORIGIN})


def test_no_referrer_last_wins() -> None:
    assert parse_referrer_policy(["strict-origin-when-cross-origin, no-referrer"]).effective is NO_REFERRER


def test_two_header_lines_read_as_one_list() -> None:
    header = parse_referrer_policy(["unsafe-url", "no-referrer"])
    assert header == ReferrerPolicyHeader(NO_REFERRER, frozenset({UNSAFE_URL, NO_REFERRER}))


def test_spaces_and_tabs_around_tokens_ignored() -> None:
    assert parse_referrer_policy(["unsafe-url ,\tno-referrer "]).effective is NO_REFERRER


def test_case_ignored() -> None:
    assert parse_referrer_policy(["NO-REFERRER"]).effective is NO_REFERRER
    assert parse_referrer_policy(["Unsafe-URL"]).effective is UNSAFE_URL


def test_no_header() -> None:
    assert parse_referrer_policy([]) == ReferrerPolicyHeader(None, frozenset())


# *******************************************
# Skipped tokens
# *******************************************


def test_unknown_token_after_known_one_skipped() -> None:
    header = parse_referrer_policy(["no-referrer, made-up-policy"])
    assert header == ReferrerPolicyHeader(NO_REFERRER, frozenset({NO_REFERRER}))


def test_only_unknown_token_gives_no_policy() -> None:
    assert parse_referrer_policy(["made-up-policy"]) == ReferrerPolicyHeader(None, frozenset())


def test_empty_value_gives_no_policy() -> None:
    assert parse_referrer_policy([""]) == ReferrerPolicyHeader(None, frozenset())


def test_empty_tokens_skipped() -> None:
    assert parse_referrer_policy([",,"]) == ReferrerPolicyHeader(None, frozenset())
    assert parse_referrer_policy(["no-referrer,,"]).effective is NO_REFERRER


@pytest.mark.parametrize(
    "lookalike",
    ["no-referrer-x", "no referrer", '"no-referrer"', "no-referrer;"],
)
def test_lookalike_tokens_not_recognized(lookalike: str) -> None:
    header = parse_referrer_policy([f"unsafe-url, {lookalike}"])
    assert header == ReferrerPolicyHeader(UNSAFE_URL, frozenset({UNSAFE_URL}))
