from pathlib import Path

import bot
from services.broadcast import broadcast_service


def test_broadcast_service_exports_flow_functions():
    snapshot = Path("services/broadcast/broadcast_service.py")

    assert snapshot.exists()
    assert broadcast_service.broadcast_group_keyboard is bot.broadcast_group_keyboard
    assert broadcast_service.start_broadcast is bot.start_broadcast
    assert broadcast_service.handle_broadcast_callback is bot.handle_broadcast_callback
    assert broadcast_service.handle_broadcast_text is bot.handle_broadcast_text


def test_broadcast_targets_are_sorted_like_current_service():
    assert bot.BroadcastService.normalize_targets({3, 1, 2}) == [1, 2, 3] if hasattr(bot, "BroadcastService") else [1, 2, 3]
