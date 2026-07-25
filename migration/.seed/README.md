# Local database seed

Populates the development Postgres with a browsable dataset by calling the **real ledger services** —
every seeded transaction goes through double-entry validation, the incremental `current_balance`
update and receivable inference.

This is not a test fixture: integration tests keep using testcontainers with an isolated session.

## Running it

```bash
make db/bootstrap     # db-only + migrations + seed (the path for a new dev)

make db/seed          # populate (idempotent: running it again duplicates nothing)
make db/seed/reset    # wipe seed data and recreate it
make docker/db/seed   # populate from inside the app container
```

Requires migrations applied (`make migration/apply`) and the database variables set in `.env`.

## What gets created

| Resource | Content |
|---|---|
| Entities | `seed-merchant-01`, `seed-platform-01`, `seed-operator-01`, `seed-baas-a`, `seed-baas-b`, `seed-customer-01` |
| Accounts | each entity's template chart of accounts, plus `9.9.901/902/903` (clearing) on the merchant and both BaaS customers |
| Sales | 4 on the merchant (300, 100, 500, 150), each with 2% MDR and a 10% platform fee, plus the fee counterpart on the platform's books |
| Receivables | `SETTLED` (sale 01), `PENDING` (sales 02 and 03), `CANCELLED` (sale 04) |
| Anticipation | on sale 01's receivable, 1.5% fee |
| Settlement | of that same receivable, over `CIP-PIX`, for `net − fee` so `1.1.002` ends at zero |
| Reversal | of sale 04 → a `REVERSAL` transaction plus a cancelled receivable |
| Deposits/withdrawals | 1,000 deposit on `baas-a` and 500 on `baas-b` (STR); 250 withdrawal on `baas-a` (CIP-PIX) |
| Transfer | `baas-a → baas-b` of 150 (internal PIX, two transactions in a single commit) |
| Periods | first day of the previous and of the current month, both `OPEN` |
| Snapshot | one on `baas-a`/`1.1.001` at D−60, to exercise the statement's snapshot-based opening balance |

Dates are relative to `date.today()`, so the dataset always lands inside a useful statement window.

## Idempotency and reset

- Re-running is safe: idempotency keys are fixed (`seed:sale:01`, `seed:transfer:01`, …) and the script
  detects already-created entities by the `seed-` prefix.
- `--reset` deletes **only** entities matching `external_id LIKE 'seed-%'` and periods matching
  `notes LIKE 'seed:%'`, in FK order. It never TRUNCATEs — your own manual data, outside the prefix, survives.

## Environment guard

The script aborts when `ENV` is not one of `dev`/`test`/`local`, or when `DATABASE_ENDPOINT` does not
look like a local host. `--force` bypasses it; `--force --reset` together require typed confirmation.

## Known limitations

- **No `PENDING` transaction** — `TransactionService.post()` always writes `COMMITTED`, so there is no
  sample data for `POST /transactions/{id}/void`.
- **Periods stay `OPEN`** — closing or locking a period would block postings on the same date, so
  `close`/`lock` are not seeded.
- **No test coverage** — this is dev tooling. A signature change in `TransactionService.post`,
  `anticipate`, `settle`, `deposit`, `withdraw`, `reverse` or `TransferService.transfer` breaks the seed
  silently.

## Files

| File | Role |
|---|---|
| `seed.py` | entrypoint: environment guard, orchestration, single commit, summary |
| `dataset.py` | declarative data (entities, amounts, rates, date offsets) |
| `reset.py` | prefix-scoped cleanup |

`migration/.seed` is not an importable Python package (its name starts with a dot), which is why
`seed.py` runs as a script and inserts the repo root into `sys.path` before importing `src.*`.
