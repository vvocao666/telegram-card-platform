# Refactor Roadmap

Baseline version: `strict-v120-owner-broadcast-no-trx`

The goal is architecture cleanup only. No existing feature should be deleted, optimized, or behavior-changed during the refactor.

## Phase 1: Backup

- Confirm current working bot version.
- Create a full local backup excluding `.env`, runtime outputs, caches, and virtual environments.
- Record current test result.
- Record current file tree.
- Do not edit runtime code in this phase.

## Phase 2: Create Directories

- Ensure target directories exist:
  - `config/`
  - `handlers/`
  - `services/ocr/`
  - `services/ledger/`
  - `services/broadcast/`
  - `services/forward/`
  - `services/price/`
  - `storage/repositories/`
  - `utils/`
  - `tests/`
  - `docs/`
  - `systemd/`
  - `scripts/`
- Add only empty or import-safe files.
- Run tests.

## Phase 3: Copy Code

- Copy functions into target modules first.
- Keep original functions in place during the first pass.
- Do not change call sites yet.
- Prefer exact code copies over rewrites.
- Run tests.

## Phase 4: Modify Imports

- Switch one feature area at a time from `bot.py` to the new module.
- Start with low-risk pure helpers.
- Move Telegram handlers only after service functions are stable.
- Preserve handler registration order.
- Run tests after each import change.

## Phase 5: Test

- Run `python -m pytest`.
- Run `python -m py_compile bot.py ledger_commands.py ledger_storage.py`.
- Add focused regression tests only when a moved boundary has no coverage.
- Do not deploy until local tests pass.

## Phase 6: GitHub Commit

- Review `git diff`.
- Confirm `.env`, database files, outputs, logs, backups, and caches are ignored.
- Commit with a clear message.
- Push to GitHub only after tests pass.
- Keep rollback instructions in the commit notes or release summary.
