from __future__ import annotations

import os

from dotenv import load_dotenv
import uvicorn

from services.card_manager.api import create_card_manager_app
from storage.repositories.card_manager_storage import CardManagerStore


def main() -> None:
    load_dotenv()
    database_path = os.getenv("CARD_MANAGER_DB_PATH", os.getenv("LEDGER_DB_PATH", "outputs/ledger.sqlite3"))
    token = os.getenv("CARD_MANAGER_API_TOKEN", "").strip()
    host = os.getenv("CARD_MANAGER_API_HOST", "127.0.0.1")
    port = int(os.getenv("CARD_MANAGER_API_PORT", "8787"))
    app = create_card_manager_app(CardManagerStore(database_path), api_token=token)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
