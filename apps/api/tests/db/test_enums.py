import typing

from app.api.schemas import common
from app.clients import base
from app.db import enums


def test_persisted_states_match_the_api_contract() -> None:
    assert {k.value for k in enums.RunKind} == {k.value for k in common.RunKind}
    assert {s.value for s in enums.RunState} == {s.value for s in common.RunState}
    assert {s.value for s in enums.StepState} == {s.value for s in common.StepState}


def test_call_status_matches_the_clients() -> None:
    assert {s.value for s in enums.CallStatus} == set(typing.get_args(base.CallStatus))


def test_send_statuses() -> None:
    assert {s.value for s in enums.SendStatus} == {
        "pending",
        "sent",
        "suppressed_test_mode",
        "failed",
        "unknown",
    }
