from types import SimpleNamespace

from services.ledger.message_identity import actor_from_message


def test_actor_from_message_prefers_regular_user() -> None:
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=7, username="user", first_name="Normal", last_name="User"),
        sender_chat=SimpleNamespace(id=-100, username="group", title="Group"),
    )

    actor = actor_from_message(message)

    assert actor is not None
    assert actor.user_id == 7
    assert actor.label == "@user"
    assert actor.display_name == "Normal User"


def test_actor_from_message_supports_anonymous_sender_chat() -> None:
    message = SimpleNamespace(
        from_user=None,
        sender_chat=SimpleNamespace(id=-100, username=None, title="锤蛋小火箭."),
    )

    actor = actor_from_message(message)

    assert actor is not None
    assert actor.user_id == -100
    assert actor.label == "锤蛋小火箭."


def test_actor_from_message_supports_forwarded_hidden_user() -> None:
    message = SimpleNamespace(
        from_user=None,
        sender_chat=None,
        forward_origin=SimpleNamespace(
            sender_user=None,
            sender_chat=None,
            chat=None,
            sender_user_name="隐藏用户",
        ),
    )

    actor = actor_from_message(message)

    assert actor is not None
    assert actor.user_id == 0
    assert actor.label == "隐藏用户"


def test_actor_from_message_supports_forwarded_chat() -> None:
    message = SimpleNamespace(
        from_user=None,
        sender_chat=None,
        forward_origin=SimpleNamespace(
            sender_user=None,
            sender_chat=SimpleNamespace(id=-200, username="source", title="来源群"),
        ),
    )

    actor = actor_from_message(message)

    assert actor is not None
    assert actor.user_id == -200
    assert actor.label == "@source"
