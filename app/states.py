from aiogram.fsm.state import State, StatesGroup


class Search(StatesGroup):
    query = State()


class AI(StatesGroup):
    chat = State()
    photo = State()
    custom = State()


class Order(StatesGroup):
    name = State()
    phone = State()
