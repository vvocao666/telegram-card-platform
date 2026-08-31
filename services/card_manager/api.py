from __future__ import annotations

"""卡密管理端 REST/WebSocket 服务。

该服务独立运行，不会被 Telegram OCR 主进程依赖。桌面端关闭或 API 不可用时，
机器人仍只写 SQLite 旁路数据并照常回复 Telegram。
"""

import asyncio
from io import BytesIO
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageOps
from pydantic import BaseModel, Field

from storage.repositories.card_manager_storage import CardManagerStore


class CardPatch(BaseModel):
    final_card: str | None = None
    denomination: str | None = Field(default=None, min_length=1, max_length=60)
    stocked: bool | None = None
    redeemed: bool | None = None
    invalid: bool | None = None
    viewed: bool | None = None
    note: str | None = Field(default=None, max_length=300)


class InsertCardRequest(BaseModel):
    direction: Literal["above", "below"]
    denomination: str | None = Field(default=None, min_length=1, max_length=60)


class ManualCardRequest(BaseModel):
    final_card: str = Field(min_length=1, max_length=200)
    denomination: str = Field(min_length=1, max_length=60)
    chat_name: str = Field(min_length=1, max_length=200)
    user_name: str = Field(min_length=1, max_length=200)


class BatchCardPatch(BaseModel):
    record_ids: list[int] = Field(min_length=1, max_length=500)
    denomination: str | None = Field(default=None, min_length=1, max_length=60)
    stocked: bool | None = None
    redeemed: bool | None = None
    invalid: bool | None = None


class BatchCardDelete(BaseModel):
    record_ids: list[int] = Field(min_length=1, max_length=10000)


class AliasRequest(BaseModel):
    display_name: str = Field(max_length=200)


class DenominationRuleRequest(BaseModel):
    prefix: str = Field(min_length=1, max_length=30)
    denomination: str = Field(min_length=1, max_length=60)


def create_card_manager_app(store: CardManagerStore, *, api_token: str) -> FastAPI:
    if not api_token:
        raise RuntimeError("CARD_MANAGER_API_TOKEN must be configured before starting the management API")
    app = FastAPI(title="Card Manager API", version="1.0")

    def require_token(x_card_manager_token: str | None = Header(default=None)) -> None:
        if x_card_manager_token != api_token:
            raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/health")
    def health(_: None = Depends(require_token)) -> dict[str, object]:
        return {"ok": True, "version": store.current_change_version(), **store.health_summary()}

    @app.get("/records")
    def records(
        chat_id: int | None = None,
        denomination: str | None = None,
        stocked: bool | None = None,
        redeemed: bool | None = None,
        duplicates_only: bool = False,
        search: str = "",
        after_version: int = 0,
        limit: int = Query(default=2000, ge=1, le=10000),
        _: None = Depends(require_token),
    ) -> dict[str, object]:
        return {
            "version": store.current_change_version(),
            "health": store.health_summary(),
            "records": store.list_records(
                chat_id=chat_id,
                denomination=denomination,
                stocked=stocked,
                redeemed=redeemed,
                duplicates_only=duplicates_only,
                search=search,
                after_version=after_version,
                limit=limit,
            ),
        }

    @app.get("/sync")
    def sync(after_version: int = Query(default=0, ge=0), _: None = Depends(require_token)) -> dict[str, object]:
        return store.changes_since(after_version)

    @app.get("/groups")
    def groups(_: None = Depends(require_token)) -> dict[str, object]:
        return {"groups": store.list_chat_counts()}

    @app.delete("/groups/{chat_id}/records")
    def clear_group_records(chat_id: int, _: None = Depends(require_token)) -> dict[str, int]:
        return {"deleted": store.clear_chat_records(chat_id)}

    @app.get("/statistics")
    def statistics(
        chat_id: int | None = None,
        denomination: str | None = None,
        stocked: bool | None = None,
        redeemed: bool | None = None,
        duplicates_only: bool = False,
        search: str = "",
        _: None = Depends(require_token),
    ) -> dict[str, int]:
        return store.statistics(
            chat_id=chat_id,
            denomination=denomination,
            stocked=stocked,
            redeemed=redeemed,
            duplicates_only=duplicates_only,
            search=search,
        )

    @app.get("/records/{record_id}/image")
    def image(record_id: int, preview: bool = True, _: None = Depends(require_token)) -> Response:
        record = store.get_record(record_id)
        path = Path(str(record["original_image_path"] or ""))
        if not path.is_file():
            raise HTTPException(status_code=410, detail="原始图片缓存已过期（仅保留当天）")
        if preview:
            # 只由独立管理端 API 生成查看预览，不接入机器人或 OCR 流程。
            try:
                with Image.open(path) as source:
                    preview_image = ImageOps.exif_transpose(source).convert("RGB")
                    preview_image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                    output = BytesIO()
                    preview_image.save(output, format="JPEG", quality=82, optimize=True)
                return Response(
                    content=output.getvalue(),
                    media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=86400"},
                )
            except (OSError, ValueError):
                # 格式异常时仍返回原始文件，保证旧图片也可继续查看。
                pass
        return FileResponse(path)

    @app.patch("/records/batch")
    def patch_records_batch(payload: BatchCardPatch, _: None = Depends(require_token)) -> list[dict[str, object]]:
        try:
            return store.update_cards_batch(
                payload.record_ids,
                **payload.model_dump(exclude_none=True, exclude={"record_ids"}),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Card record not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.patch("/records/{record_id}")
    def patch_record(record_id: int, payload: CardPatch, _: None = Depends(require_token)) -> dict[str, object]:
        try:
            return store.update_card(record_id, **payload.model_dump(exclude_none=True))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Card record not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/records/{record_id}/insert")
    def insert_record(record_id: int, payload: InsertCardRequest, _: None = Depends(require_token)) -> dict[str, object]:
        try:
            return store.insert_manual_card(
                record_id,
                after=payload.direction == "below",
                denomination=payload.denomination,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Card record not found") from exc

    @app.post("/records/manual")
    def create_manual_record(payload: ManualCardRequest, _: None = Depends(require_token)) -> dict[str, object]:
        """创建仅供管理端展示的手动卡密，不参与 Telegram 或 OCR。"""
        try:
            return store.create_manual_card(
                final_card=payload.final_card,
                denomination=payload.denomination,
                chat_name=payload.chat_name,
                user_name=payload.user_name,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.delete("/records/batch")
    def delete_records_batch(payload: BatchCardDelete, _: None = Depends(require_token)) -> dict[str, int]:
        """管理端批量隐藏卡密；只修改旁路表，绝不影响机器人或 Telegram。"""
        return {"deleted": store.delete_cards(payload.record_ids)}

    @app.post("/records/batch/restore")
    def restore_records_batch(payload: BatchCardDelete, _: None = Depends(require_token)) -> list[dict[str, object]]:
        """撤销管理端误删；不会重新处理图片、OCR 或 Telegram 消息。"""
        return store.restore_deleted_cards(payload.record_ids)

    @app.delete("/records/{record_id}")
    def delete_record(record_id: int, _: None = Depends(require_token)) -> dict[str, bool]:
        if not store.delete_card(record_id):
            raise HTTPException(status_code=404, detail="Card record not found or already deleted")
        return {"deleted": True}

    @app.put("/aliases/chats/{chat_id}")
    def chat_alias(chat_id: int, payload: AliasRequest, _: None = Depends(require_token)) -> dict[str, bool]:
        store.set_chat_alias(chat_id, payload.display_name)
        return {"ok": True}

    @app.put("/aliases/users/{user_id}")
    def user_alias(user_id: int, payload: AliasRequest, _: None = Depends(require_token)) -> dict[str, bool]:
        store.set_user_alias(user_id, payload.display_name)
        return {"ok": True}

    @app.get("/denomination-rules")
    def denomination_rules(_: None = Depends(require_token)) -> dict[str, object]:
        return {"rules": store.list_denomination_rules()}

    @app.put("/denomination-rules")
    def put_denomination_rule(payload: DenominationRuleRequest, _: None = Depends(require_token)) -> dict[str, bool]:
        store.set_denomination_rule(payload.prefix, payload.denomination)
        return {"ok": True}

    @app.delete("/denomination-rules/{prefix}")
    def remove_denomination_rule(prefix: str, _: None = Depends(require_token)) -> dict[str, bool]:
        return {"deleted": store.delete_denomination_rule(prefix)}

    @app.websocket("/ws")
    async def websocket(websocket: WebSocket) -> None:
        if websocket.query_params.get("token") != api_token:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        version = max(0, int(websocket.query_params.get("after_version", "0")))
        try:
            while True:
                changes = await asyncio.to_thread(store.changes_since, version)
                next_version = int(changes["version"])
                if next_version > version:
                    await websocket.send_json(changes)
                    version = next_version
                await asyncio.sleep(1.0)
        except (WebSocketDisconnect, ValueError):
            return

    return app
