from aiogram.fsm.state import State, StatesGroup


class Account(StatesGroup):
    session_name = State()
    api_id = State()
    api_hash = State()
    phone = State()
    code = State()
    password = State()
    delete_choice = State()


class Group(StatesGroup):
    source = State()
    target = State()
    delete_type = State()
    delete_choice = State()


class Parser(StatesGroup):
    select_account = State()
    select_group = State()
    messages_limit = State()
    resume_choice = State()


class Inviter(StatesGroup):
    select_account = State()
    select_target = State()


class Broadcaster(StatesGroup):
    select_account = State()
    select_source = State()
    messages_limit = State()
    message_text = State()


class PublicGroup(StatesGroup):
    add_link = State()
    add_region = State()
    parse_account = State()
    parse_select = State()
    parse_limit = State()
    parse_resume = State()
    select_for_export = State()
    delete_choice = State()


class PublicInviter(StatesGroup):
    select_publics = State()
    select_account = State()
    select_target = State()