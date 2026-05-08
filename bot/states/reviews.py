"""FSM states for collecting client reviews."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class ReviewStates(StatesGroup):
    """States for one-step review text collection."""

    waiting_for_text = State()
