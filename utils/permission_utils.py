from __future__ import annotations

from services.runtime import is_owner_update, update_is_from_owner


def is_owner(user_id: int | None, owner_ids: set[int]) -> bool:
    return user_id is not None and user_id in owner_ids
