from __future__ import annotations

import asyncio

from services.ocr.batch_processor import LiveOcrBatchProgress


class FakeProgressMessage:
    def __init__(self, text: str) -> None:
        self.texts = [text]
        self.deleted = False

    async def edit_text(self, text: str) -> None:
        self.texts.append(text)

    async def delete(self) -> None:
        self.deleted = True


class FakeMessage:
    def __init__(self) -> None:
        self.progress_message: FakeProgressMessage | None = None

    async def reply_text(self, text: str) -> FakeProgressMessage:
        self.progress_message = FakeProgressMessage(text)
        return self.progress_message


def test_live_progress_starts_on_first_image_and_tracks_received_and_done() -> None:
    async def run_case() -> None:
        now = {"value": 100.0}
        message = FakeMessage()
        progress = LiveOcrBatchProgress(
            message,
            enabled=lambda: True,
            update_seconds=lambda: 0.1,
            clock=lambda: now["value"],
            logger=type("Logger", (), {"exception": lambda *args: None, "info": lambda *args: None})(),
        )

        progress.register_image(message)
        await progress.publish()
        assert message.progress_message is not None
        assert message.progress_message.texts[-1].endswith("处理进度：0/1")

        now["value"] += 1
        progress.register_image(message)
        await progress.publish()
        assert "已收到：2张" in message.progress_message.texts[-1]

        now["value"] += 1
        await progress.mark_done()
        assert message.progress_message.texts[-1].endswith("处理进度：1/2")
        now["value"] += 1
        await progress.mark_done()
        assert message.progress_message.texts[-1].endswith("处理进度：2/2")

        await progress.finish(True)
        assert message.progress_message.deleted is True

    asyncio.run(run_case())
