from __future__ import annotations

"""Public, password-protected mobile view for the independent card manager.

This process is deliberately separate from both the Telegram bot and the
localhost-only desktop-management API.  It only exposes the same sidecar store
through a mobile page after HTTP Basic authentication.
"""

import base64
import asyncio
import hmac
import os
from pathlib import Path
import secrets
import time

from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from services.card_manager.api import create_card_manager_app
from storage.repositories.card_manager_storage import CardManagerStore


WEB_USERNAME = "cardadmin"
SESSION_COOKIE = "card_manager_mobile_session"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 30

LOGIN_PAGE = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>卡密管理登录</title><style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f5f6fa;color:#172033;font:15px -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}.card{width:min(360px,calc(100vw - 40px));padding:26px;background:#fff;border:1px solid #e4e7ec;border-radius:20px;box-shadow:0 12px 36px #10182812}h1{margin:0 0 7px;font-size:25px}.sub{color:#667085;font-size:13px;margin-bottom:22px}input,button{box-sizing:border-box;width:100%;font:inherit;border-radius:11px}input{padding:12px;border:1px solid #d3d8e2;outline-color:#007aff}button{margin-top:10px;border:0;padding:12px;background:#007aff;color:#fff;font-weight:800}.error{min-height:19px;margin-top:10px;color:#d70015;font-size:13px}</style></head><body><form class="card" id="login"><h1>卡密管理</h1><div class="sub">请输入管理网页登录密码</div><input id="password" type="password" autocomplete="current-password" placeholder="登录密码" autofocus><button>登录</button><div class="error" id="error"></div></form><script>document.querySelector('#login').onsubmit=async e=>{e.preventDefault();const error=document.querySelector('#error'),button=e.currentTarget.querySelector('button');error.textContent='';button.textContent='正在登录…';button.disabled=true;try{const r=await fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:document.querySelector('#password').value})});if(!r.ok)throw new Error();location.replace('/mobile/')}catch(_){error.textContent='密码不正确，请重新输入。';button.textContent='登录';button.disabled=false}};</script></body></html>"""


def create_mobile_web_app(
    store: CardManagerStore,
    *,
    api_token: str,
    web_password: str,
    web_directory: Path,
) -> FastAPI:
    if not web_password:
        raise RuntimeError("CARD_MANAGER_WEB_PASSWORD must be configured before starting the mobile web")
    expected_authorization = "Basic " + base64.b64encode(
        f"{WEB_USERNAME}:{web_password}".encode("utf-8")
    ).decode("ascii")
    # 会话签名由网页登录密码与管理端令牌共同派生；服务重启后仍然有效，
    # 但改密码或过期后会自动失效。不会把令牌暴露给浏览器。
    session_secret = f"{web_password}\0{api_token}".encode("utf-8")

    def issue_session() -> str:
        payload = f"{int(time.time())}.{secrets.token_urlsafe(16)}"
        signature = hmac.new(session_secret, payload.encode("utf-8"), "sha256").hexdigest()
        return f"{payload}.{signature}"

    def valid_session(session: str) -> bool:
        try:
            timestamp, nonce, signature = session.rsplit(".", 2)
            issued_at = int(timestamp)
        except (TypeError, ValueError):
            return False
        payload = f"{timestamp}.{nonce}"
        expected = hmac.new(session_secret, payload.encode("utf-8"), "sha256").hexdigest()
        age = int(time.time()) - issued_at
        return 0 <= age <= SESSION_TTL_SECONDS and hmac.compare_digest(signature, expected)

    api_app = create_card_manager_app(store, api_token=api_token)
    app = FastAPI(title="Card Manager Mobile Web", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def require_web_login(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.url.path == "/login":
            return await call_next(request)
        authorization = request.headers.get("authorization", "")
        session = request.cookies.get(SESSION_COOKIE, "")
        is_authorized = valid_session(session) or hmac.compare_digest(authorization, expected_authorization)
        if not is_authorized:
            if request.url.path.startswith("/api/"):
                return PlainTextResponse("登录已失效。", status_code=401)
            return RedirectResponse(url="/login", status_code=307)
        # The public page never receives the API token.  It is only injected
        # into the in-process API call after the password has been checked.
        request.scope["headers"] = list(request.scope["headers"]) + [
            (b"x-card-manager-token", api_token.encode("utf-8")),
        ]
        return await call_next(request)

    @app.get("/login", include_in_schema=False)
    def login_page(request: Request):
        if valid_session(request.cookies.get(SESSION_COOKIE, "")):
            return RedirectResponse(url="/mobile/")
        return HTMLResponse(LOGIN_PAGE, headers={"Cache-Control": "no-store"})

    @app.post("/login", include_in_schema=False)
    async def login(request: Request) -> JSONResponse:
        try:
            password = str((await request.json()).get("password", ""))
        except ValueError:
            password = ""
        if not hmac.compare_digest(password, web_password):
            return JSONResponse({"ok": False}, status_code=401)
        session = issue_session()
        response = JSONResponse({"ok": True})
        response.set_cookie(SESSION_COOKIE, session, max_age=SESSION_TTL_SECONDS, httponly=True, secure=True, samesite="strict")
        return response

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/mobile/")

    @app.websocket("/ws")
    async def live_changes(websocket: WebSocket) -> None:
        """登录后的手机网页实时变更通知，不向浏览器暴露管理 API 密钥。"""
        session = websocket.cookies.get(SESSION_COOKIE, "")
        authorization = websocket.headers.get("authorization", "")
        if not valid_session(session) and not hmac.compare_digest(authorization, expected_authorization):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        version = max(0, int(websocket.query_params.get("after_version", "0")))
        try:
            while True:
                changes = await asyncio.to_thread(store.changes_since, version)
                next_version = int(changes["version"])
                if next_version > version:
                    # 网页收到版本变化后合并一次刷新；避免过去每 5 秒全量请求。
                    await websocket.send_json({"version": next_version})
                    version = next_version
                await asyncio.sleep(1.0)
        except (WebSocketDisconnect, ValueError):
            return

    app.mount("/api", api_app)
    app.mount("/mobile", StaticFiles(directory=str(web_directory), html=True), name="mobile")
    return app


def main() -> None:
    load_dotenv()
    database_path = os.getenv("CARD_MANAGER_DB_PATH", os.getenv("LEDGER_DB_PATH", "outputs/ledger.sqlite3"))
    api_token = os.getenv("CARD_MANAGER_API_TOKEN", "").strip()
    web_password = os.getenv("CARD_MANAGER_WEB_PASSWORD", "").strip()
    host = os.getenv("CARD_MANAGER_WEB_HOST", "0.0.0.0")
    port = int(os.getenv("CARD_MANAGER_WEB_PORT", "8788"))
    web_directory = Path(__file__).with_name("web")
    app = create_mobile_web_app(
        CardManagerStore(database_path),
        api_token=api_token,
        web_password=web_password,
        web_directory=web_directory,
    )
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
