# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the ODPi Egeria project.
"""The element statuses Egeria accepts in a `limitResultsByStatus` filter, and the check that keeps others out.

`limitResultsByStatus` filters on an element's *header* status, Egeria's `ElementStatus` enum. It is not the
`contentStatus` / `activityStatus` / `deploymentStatus` property an authored element, action or deployed thing
carries. A value from one of those (DRAFT, APPROVED, UNDER_DEVELOPMENT, ...) used to reach Egeria and come back
as a 400 ("Cannot deserialize value of type ElementStatus from String "DRAFT""), seen 2026-11-13 from a find
whose caller meant "draft governance definitions". pyegeria now refuses it before sending, and says what the
value is and which property to filter on instead.

This module imports nothing from pyegeria, so the request-body models can use it without an import cycle.
"""
from __future__ import annotations

from typing import Iterable, List, Optional

#: Egeria's ElementStatus values, from ElementStatus.java at odpi/egeria 3c8970b656 (2026-09-21), the enum
#: in the build laz runs (002a3ef1, 2026-11-13). Older Egerias (5.x) accepted more (DRAFT, PROPOSED,
#: APPROVED, ...): when Egeria's enum changes, change this set and name the new source.
ELEMENT_STATUSES = frozenset({"UNKNOWN", "ACTIVE", "INVALID", "DELETED", "OTHER"})
ELEMENT_STATUS_SOURCE = "ElementStatus.java @ odpi/egeria 3c8970b656"

# The status properties a misplaced value most likely belongs to: the type-specific enums
# (ContentStatus, ActivityStatus, DeploymentStatus), as md_processing's element_status.VALID_STATUS_VALUES.
_OTHER_STATUS_ENUMS = (
    ("content", "contentStatus", frozenset({"DRAFT", "PREPARED", "PROPOSED", "APPROVED", "REJECTED", "ACTIVE",
                                             "DEPRECATED", "OBSOLETE", "OTHER"})),
    ("activity", "activityStatus", frozenset({"REQUESTED", "APPROVED", "WAITING", "ACTIVATING", "IN_PROGRESS",
                                               "PAUSED", "FOR_INFO", "COMPLETED", "INVALID", "IGNORED", "FAILED",
                                               "CANCELLED", "ABANDONED", "OTHER"})),
    ("deployment", "deploymentStatus", frozenset({"PROPOSED", "UNDER_DEVELOPMENT", "DEVELOPMENT_COMPLETE",
                                                   "APPROVED_FOR_DEPLOYMENT", "REJECTED_FOR_DEPLOYMENT", "STANDBY",
                                                   "ACTIVE", "DISABLED", "FAILED", "OTHER"})),
)


class InvalidElementStatus(ValueError):
    """A `limitResultsByStatus` value that isn't one of Egeria's element statuses. A ValueError, so a pydantic
    validator reports it as a field error (which pyegeria turns into PyegeriaInvalidParameterException)."""


def _why(value: str) -> str:
    kinds = [(kind, prop) for kind, prop, values in _OTHER_STATUS_ENUMS if value in values]
    if not kinds:
        return f"{value} is not an element status"
    names = " or ".join(kind for kind, _ in kinds)
    props = " or ".join(prop for _, prop in kinds)
    return f"{value} is a {names} status, not an element status; filter on {props} instead"


def check_element_statuses(values: Optional[Iterable[str]], *, field: str = "limit_results_by_status"
                           ) -> Optional[List[str]]:
    """`values` upper-cased, or InvalidElementStatus naming each value that isn't an element status and what it
    is. None and an empty list pass through unchanged (no status filter). A lone string counts as one value."""
    if values is None:
        return None
    if isinstance(values, str):
        values = [values]
    out: List[str] = []
    bad: List[str] = []
    for v in values:
        s = str(v).strip().upper()
        if s in ELEMENT_STATUSES:
            out.append(s)
        else:
            bad.append(_why(s or repr(v)))
    if bad:
        raise InvalidElementStatus(
            f"{field}: {'; '.join(bad)}. Element statuses are {', '.join(sorted(ELEMENT_STATUSES))} "
            f"({ELEMENT_STATUS_SOURCE}).")
    return out
