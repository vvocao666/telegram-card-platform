from __future__ import annotations

"""定时清理仅供管理端核对的过期卡密记录。"""

import os

from dotenv import load_dotenv

from storage.repositories.card_manager_storage import CardManagerStore


def main() -> None:
    load_dotenv()
    database_path = os.getenv("CARD_MANAGER_DB_PATH", os.getenv("LEDGER_DB_PATH", "outputs/ledger.sqlite3"))
    removed = CardManagerStore(database_path).purge_records_before_previous_day()
    print(f"card-manager-prune: removed={removed}")


if __name__ == "__main__":
    main()
