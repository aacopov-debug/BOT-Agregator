"""FSM States для личного кабинета."""

from aiogram.fsm.state import State, StatesGroup


class NoteState(StatesGroup):
    waiting_note = State()
