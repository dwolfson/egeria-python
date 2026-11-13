# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the ODPi Egeria project.
"""`limitResultsByStatus` takes Egeria's ElementStatus only; anything else is refused in words, before sending.

Seen 2026-11-13 17:32:01Z on laz: a draft-spec preview passed limit_result_by_status ["DRAFT", ...] through to
GovernanceOfficer.find_governance_definitions, and Egeria answered 400 ("Cannot deserialize value of type
ElementStatus from String "DRAFT""). DRAFT is a content status; the header-status filter never accepted it.
"""
import json
from pathlib import Path

import pytest

from pyegeria.core._exceptions import PyegeriaInvalidParameterException
from pyegeria.models.element_status import (ELEMENT_STATUSES, ELEMENT_STATUS_SOURCE, InvalidElementStatus,
                                            check_element_statuses)
from pyegeria.models.models import FilterRequestBody, SearchStringRequestBody
from pyegeria.view.format_set_executor import _normalize_report_params

pytestmark = pytest.mark.unit
REPO = Path(__file__).resolve().parents[2]


def test_the_constant_is_egerias_element_status_enum_and_names_its_source():
    assert ELEMENT_STATUSES == {"UNKNOWN", "ACTIVE", "INVALID", "DELETED", "OTHER"}
    assert "ElementStatus.java" in ELEMENT_STATUS_SOURCE and "3c8970b656" in ELEMENT_STATUS_SOURCE


def test_element_statuses_pass_upper_cased_and_no_filter_stays_no_filter():
    body = SearchStringRequestBody.model_validate(
        {"class": "SearchStringRequestBody", "limitResultsByStatus": ["active", " Deleted "]})
    assert body.limit_results_by_status == ["ACTIVE", "DELETED"]
    for value in (None, []):
        assert check_element_statuses(value) == value
    assert FilterRequestBody.model_validate({"class": "FilterRequestBody"}).limit_results_by_status is None


def test_draft_is_refused_as_a_content_status_in_the_request_body():
    with pytest.raises(ValueError) as caught:
        SearchStringRequestBody.model_validate({"class": "SearchStringRequestBody", "limitResultsByStatus": ["DRAFT"]})
    assert "DRAFT is a content status, not an element status; filter on contentStatus instead" in str(caught.value)


def test_each_wrong_value_is_named_with_what_it_is():
    with pytest.raises(InvalidElementStatus) as caught:
        check_element_statuses(["ACTIVE", "APPROVED", "UNDER_DEVELOPMENT", "APPROVED_CONCEPT"])
    words = str(caught.value)
    assert "APPROVED is a content or activity status, not an element status; filter on contentStatus or " \
           "activityStatus instead" in words
    assert "UNDER_DEVELOPMENT is a deployment status, not an element status; filter on deploymentStatus" in words
    assert "APPROVED_CONCEPT is not an element status" in words          # the old (5.x) enum's values
    assert "ACTIVE is" not in words                                        # a valid value isn't complained about
    assert "Element statuses are ACTIVE, DELETED, INVALID, OTHER, UNKNOWN" in words


@pytest.mark.parametrize("key", ["limit_result_by_status", "limit_results_by_status"])
def test_a_report_run_refuses_before_any_client_is_built(key):
    with pytest.raises(InvalidElementStatus, match="DRAFT is a content status"):
        _normalize_report_params({key: "['DRAFT', 'ACTIVE']"})               # the Dr.Egeria / form string shape
    assert _normalize_report_params({key: "ACTIVE"})["limit_results_by_status"] == ["ACTIVE"]


class _Response:
    def json(self):
        return {"elements": []}


@pytest.mark.asyncio
async def test_the_sdk_find_the_preview_reached_refuses_without_sending(monkeypatch):
    from pyegeria.omvs.governance_officer import GovernanceOfficer
    monkeypatch.setattr(GovernanceOfficer, "check_connection", lambda self: "test")
    client = GovernanceOfficer("view-server", "https://localhost:1", "user", "pwd")
    sent = []

    async def fake_make_request(method, url, body=None, *a, **k):
        sent.append(body)
        return _Response()
    client._async_make_request = fake_make_request

    with pytest.raises(PyegeriaInvalidParameterException) as caught:
        await client._async_find_governance_definitions(
            "*", limit_results_by_status=["DRAFT", "APPROVED", "UNDER_DEVELOPMENT"], output_format="JSON")
    assert sent == []                                                      # nothing reached Egeria
    assert "DRAFT is a content status" in json.dumps(caught.value.__dict__, default=str) + str(caught.value)

    sent.clear()                                                           # a real element status still goes out
    await client._async_find_governance_definitions("*", limit_results_by_status=["ACTIVE"], output_format="JSON")
    assert sent and json.loads(sent[0])["limitResultsByStatus"] == ["ACTIVE"]


def test_the_report_commands_offer_only_element_statuses():
    spec = json.loads((REPO / "md_processing/data/compact_commands/commands_report_compact.json").read_text())
    assert set(spec["attribute_definitions"]["Limit Result by Status"]["valid_values"]) == ELEMENT_STATUSES
    seed = (REPO / "pyegeria/view/seed/Views & Reports.json").read_text()
    assert '"limit_result_by_status", "label": "Limit Result by Status", "valid_values": ["UNKNOWN", "ACTIVE", ' \
           '"INVALID", "DELETED", "OTHER"]' in seed and "APPROVED_CONCEPT" not in seed
