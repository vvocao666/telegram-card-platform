from __future__ import annotations


def is_owner(user_id: int | None, owner_ids: set[int]) -> bool:
    return user_id is not None and user_id in owner_ids


def parse_chat_id(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def update_user_is_owner(update: object | None, owner_chat_id: object) -> bool:
    owner_id = parse_chat_id(owner_chat_id)
    user = getattr(update, "effective_user", None) if update else None
    return bool(owner_id is not None and user and getattr(user, "id", None) == owner_id)


def update_user_or_chat_is_owner(update: object | None, owner_chat_id: object) -> bool:
    owner_id = parse_chat_id(owner_chat_id)
    if owner_id is None or not update:
        return False
    user = getattr(update, "effective_user", None)
    if user and getattr(user, "id", None) == owner_id:
        return True
    chat = getattr(update, "effective_chat", None)
    return bool(chat and getattr(chat, "id", None) == owner_id)
