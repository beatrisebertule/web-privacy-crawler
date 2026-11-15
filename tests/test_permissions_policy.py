"""
Tests for Q10's Permissions-Policy parsing.

Not-disabled tests all have at least one disabled feature that does get counted
so we know it's not just discarding everything.
Malformed tests all have one too, which gets thrown out with the rest of the header
"""

# Standard library imports
import importlib

# Third party imports
import pytest

# Import statement can't load a module name starting with a digit.
q10 = importlib.import_module("10_analysis")

PolicyFeatures = q10.PolicyFeatures
MalformedPermissionsPolicy = q10.MalformedPermissionsPolicy
parse_permissions_policy = q10.parse_permissions_policy


def features(disabled: set[str], named_not_disabled: set[str]) -> PolicyFeatures:
    return PolicyFeatures(frozenset(disabled), frozenset(named_not_disabled))


# *******************************************
# Disabled features
# *******************************************


def test_three_disabled_features_in_one_header() -> None:
    assert parse_permissions_policy(["camera=(), usb=(), microphone=()"]) == features(
        {"camera", "usb", "microphone"},
        set(),
    )


def test_repeated_header_lines_are_joined() -> None:
    assert parse_permissions_policy(["camera=()", "usb=()", "geolocation=(self)"]) == features(
        {"camera", "usb"},
        {"geolocation"},
    )


def test_space_inside_empty_list_is_disabled() -> None:
    assert parse_permissions_policy(["camera=( ), usb=(self)"]) == features({"camera"}, {"usb"})


def test_parameters_on_empty_list_still_disabled() -> None:
    assert parse_permissions_policy(["camera=();report-to=x"]) == features({"camera"}, set())


def test_no_header_gives_no_features() -> None:
    assert parse_permissions_policy([]) == features(set(), set())


# *******************************************
# Named, not disabled
# *******************************************


def test_self_star_and_origin_lists_are_not_disabled() -> None:
    header = 'camera=(), a=(self), b=*, c=("https://x.nl"), d=(self "https://a.nl" "https://b.nl")'
    assert parse_permissions_policy([header]) == features({"camera"}, {"a", "b", "c", "d"})


def test_repeated_key_last_value_wins() -> None:
    assert parse_permissions_policy(["usb=(), camera=(), camera=(self)"]) == features(
        {"usb"},
        {"camera"},
    )
    assert parse_permissions_policy(["usb=(), camera=(self), camera=()"]) == features(
        {"usb", "camera"},
        set(),
    )


def test_non_list_values_are_named_not_disabled() -> None:
    assert parse_permissions_policy(['a=?0, b=1, c="x", d=none, f, e=()']) == features(
        {"e"},
        {"a", "b", "c", "d", "f"},
    )


def test_empty_string_header() -> None:
    # Package parses "" as an empty dictionary, not an error.
    assert parse_permissions_policy([""]) == features(set(), set())


# *******************************************
# Malformed headers
# *******************************************


@pytest.mark.parametrize(
    "header_values",
    [
        pytest.param(["camera=(), Usb=()"], id="uppercase key"),
        pytest.param(["camera=()("], id="unclosed list"),
        pytest.param(["camera=(),"], id="trailing comma"),
        pytest.param(["camera=(), camera 'none'"], id="feature policy syntax"),
        pytest.param(["camera=(), usb=(self 'src')"], id="single-quoted origin"),
        pytest.param(["camera=(), caméra=()"], id="non-ascii key"),
        pytest.param(["camera=(), , usb=()"], id="empty member"),
    ],
)
def test_structured_field_error_rejects_whole_header(header_values: list[str]) -> None:
    with pytest.raises(MalformedPermissionsPolicy):
        parse_permissions_policy(header_values)


def test_bad_line_poisons_joined_header() -> None:
    assert parse_permissions_policy(["camera=()"]) == features({"camera"}, set())
    with pytest.raises(MalformedPermissionsPolicy, match="camera"):
        parse_permissions_policy(["camera=()", "usb=()("])


def test_empty_line_next_to_real_line_is_malformed() -> None:
    # Chromium's joined value also starts with a comma
    assert parse_permissions_policy([""]) == features(set(), set())
    with pytest.raises(MalformedPermissionsPolicy):
        parse_permissions_policy(["", "camera=()"])


def test_lone_surrogate_is_malformed_not_a_crash() -> None:
    # JSON allows an unpaired "\udcff" escape. UTF-8 can't encode it.
    with pytest.raises(MalformedPermissionsPolicy):
        parse_permissions_policy(["camera=()\udcff"])
