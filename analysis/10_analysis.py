"""
Analysis-Q10: five Permissions-Policy features disabled on most websites, mobile crawl.

Only first-party responses count. (First party is resulting page after redirects)
Feature counts as disabled if its allowlist is empty, `camera=()`.
Each website counts once per feature.
"""

# Standard library imports
from dataclasses import dataclass

# Third party imports
import http_sf

PERMISSIONS_POLICY_HEADER = "permissions-policy"
FEATURE_POLICY_HEADER = "feature-policy"


class MalformedPermissionsPolicy(ValueError):
    """Invalid Permissions-Policy syntax. Browsers ignore the whole header."""


@dataclass(frozen=True)
class PolicyFeatures:
    """
    Features named in Permissions-Policy for a single response.

    `disabled`: empty allowlist, `name=()`
    `named_not_disabled`: any other value, such as `(self)`, `*` or an origin list
    """

    disabled: frozenset[str]
    named_not_disabled: frozenset[str]


def parse_permissions_policy(header_values: list[str]) -> PolicyFeatures:
    """
    Split a response's Permissions-Policy into disabled and other features.

    example: ["camera=(), usb=(self)"] -> disabled {"camera"}, named_not_disabled {"usb"}

    :param header_values: every Permissions-Policy value on one response, in order
    :return: Disabled and named-not-disabled features, both empty if no header.
    :raises MalformedPermissionsPolicy: if header isn't a valid structured field dictionary
    """
    if not header_values:
        return PolicyFeatures(frozenset(), frozenset())

    # Repeated header lines join with a comma before parsing, as RFC 9651 says.
    joined_value = ", ".join(header_values)
    try:
        members = http_sf.parse(joined_value.encode("utf-8"), tltype="dictionary")
    except (http_sf.StructuredFieldError, UnicodeEncodeError) as parse_error:
        raise MalformedPermissionsPolicy(f"{joined_value!r}: {parse_error}") from parse_error

    disabled = set()
    named_not_disabled = set()
    for feature, (value, _parameters) in members.items():
        # Empty allowlist means no origin gets the feature. (Package returns it as an empty list)
        if isinstance(value, list) and not value:
            disabled.add(feature)
        else:
            named_not_disabled.add(feature)
    return PolicyFeatures(frozenset(disabled), frozenset(named_not_disabled))
