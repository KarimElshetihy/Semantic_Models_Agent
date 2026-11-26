"""State machine tests: every state and action pair is either a listed legal transition or refused."""

import pytest

from ssas_agent.approval import LEGAL_TRANSITIONS, TERMINAL_STATES, Action, InvalidTransitionError, State, next_state

ALL_STATES = [None, *State]


@pytest.mark.parametrize("state", ALL_STATES, ids=lambda state: state.value if state else "no-run")
@pytest.mark.parametrize("action", list(Action), ids=lambda action: action.value)
def test_only_listed_transitions_are_legal(state, action):
    key = (state, action)

    if key in LEGAL_TRANSITIONS:
        assert next_state(state, action) == LEGAL_TRANSITIONS[key]
    else:
        with pytest.raises(InvalidTransitionError):
            next_state(state, action)


@pytest.mark.parametrize("state", sorted(TERMINAL_STATES, key=lambda state: state.value))
def test_terminal_states_have_no_outgoing_transitions(state):
    assert all((state, action) not in LEGAL_TRANSITIONS for action in Action)


def test_happy_path_reaches_verified():
    path = [
        (None, Action.CREATE),
        (State.DRAFT, Action.SUBMIT),
        (State.PROPOSED, Action.APPROVE),
        (State.APPROVED, Action.APPLY),
        (State.APPLIED, Action.VERIFY_PASS),
    ]

    states = [next_state(state, action) for state, action in path]

    assert states == [State.DRAFT, State.PROPOSED, State.APPROVED, State.APPLIED, State.VERIFIED]


def test_edit_after_approval_returns_to_draft():
    assert next_state(State.APPROVED, Action.EDIT) is State.DRAFT


def test_cancel_is_refused_after_apply():
    with pytest.raises(InvalidTransitionError, match="cannot 'cancel' from APPLIED"):
        next_state(State.APPLIED, Action.CANCEL)


def test_apply_is_refused_before_approval():
    with pytest.raises(InvalidTransitionError, match="cannot 'apply' from PROPOSED"):
        next_state(State.PROPOSED, Action.APPLY)
