# Open Ledger — Full Specification

---

## Overview

A financial ledger is the immutable, authoritative record of all financial events in a system. Every balance, every fee, every transfer is traceable back to a specific entry. This document specifies the design of **Open Ledger**: a double-entry bookkeeping service built as an isolated microservice with its own database, communicating with the rest of the system exclusively through events.

The design is inspired by production ledger implementations at [Midaz](https://github.com/LerianStudio/midaz) and [Formance](https://www.formance.com/).

---

## Core Principles

### 1. Immutability
Entries are never updated or deleted. Corrections are made by posting new reversing entries. The full history is always preserved.

### 2. Double-Entry Bookkeeping
Every financial event generates at least one debit and one credit of equal value. In single-currency transactions the sum of all debits equals the sum of all credits. In multi-currency transactions the invariant is enforced **per currency**: Σ debits(currency X) = Σ credits(currency X) for every currency present in the transaction.

### 3. Transaction Header + Entries _(Midaz / Formance)_
A `transaction` is a header that groups one or more related `entries` (e.g. a sale + fee). This enables native multi-leg transactions and atomic operations — either all entries are committed or none are.

Supported statuses: `pending`, `committed`, `voided`.

### 4. Incremental Current Balance _(Midaz)_
Each account maintains a `current_balance` column updated by the application layer within the same database transaction that inserts the entries. Balance reads are a direct `SELECT` — no aggregation needed. A nightly job recalculates balances from scratch and alerts on any divergence greater than $0.01.

### 5. System Boundary Accounts _(Formance)_
The `9.9.xxx` range is reserved for system boundary accounts. Two are created automatically for every entity:

**`9.9.999 World`** — generic external boundary. Represents the outside world when the specific clearing counterparty does not matter or is not yet known. Used as a fallback for simple deployments.

**`9.9.998 Transfer`** — represents money crossing entity boundaries *within* the ledger, without leaving the system. Used for internal transfers between entities (e.g. PIX between two BaaS customers on the same platform).

For operational deployments requiring bank reconciliation, `9.9.999 World` should be replaced by typed World accounts — one per external clearing counterparty — following the same `9.9.xxx` convention:

| Code    | Name              | Represents                                      |
|---------|-------------------|-------------------------------------------------|
| 9.9.901 | World/STR         | Banco Central STR — TED and large-value wires   |
| 9.9.902 | World/CIP-PIX     | CIP — PIX settlement                            |
| 9.9.903 | World/COMPE       | COMPE — cheque clearinghouse (D+1)              |
| 9.9.904 | World/Bank-{code} | Named liquidating bank (one account per bank)   |
| 9.9.999 | World             | Generic fallback for simple or unknown cases    |

The event handler must resolve the correct World sub-account at posting time — the clearing network is known from the payment instruction. This is a ledger-layer decision: it determines which account receives the entry and cannot be corrected retroactively in an upstream layer.

System-level invariants:
- Σ all `9.9.9xx World` accounts across all entities = net money that has entered or left the system.
- Σ `9.9.998 Transfer` across all entities = **0** always — every send has a corresponding receive within the ledger.

### 6. Partial Event Sourcing _(Formance)_
Every inbound event is recorded in an `event_log` table before processing. The materialized state (accounts, balances) is derived from processing those events. Failed events can be replayed. This is not pure event sourcing — the materialized state is the source of truth for reads.

### 7. Rich Metadata
Each `transaction` and each individual `entry` carries a `metadata JSONB` field. Rates, formulas, and external references are stored at the point of calculation, not recomputed later.

### 8. Multi-Tenant
Each entity has its own isolated set of accounts. An entity is any participant in the financial system — a merchant, a customer, a platform operator, or anything else. The ledger does not enforce a type taxonomy: `entity_type` is free-form metadata, not a structural constraint. Entities are registered from events — the ledger never reads from the upstream service's database.

### 9. Multi-Currency
Each account is denominated in a single currency (`currency CHAR(3)`, ISO 4217). Entries must match the currency of the account they post to — this is enforced by the application. Cross-currency conversions use a pair of single-currency FX transit accounts as intermediaries, keeping double-entry intact per currency. The exchange rate is captured in `metadata` at the time of posting and never recomputed.

### 10. Layered Architecture — What Belongs in the Ledger

The ledger is the authoritative source of financial entries, but it is one component in a broader financial platform. Upstream layers — whether a data warehouse, an analytical pipeline, a reporting service, or any other architecture a team chooses — consume ledger data to produce aggregations, calculations, and reports that would be inappropriate to embed in the accounting core.

**The deciding criterion:**

> If a decision must be made at posting time — it determines *which account* to debit/credit, *how much*, or *whether* an entry is allowed — it belongs in the ledger.
> If it can be derived after the fact from data already in the ledger, it belongs in an upstream layer.

```
┌──────────────────────────────────────────────────────────────┐
│  UPSTREAM LAYERS                                             │
│  (reporting service, data warehouse, analytical pipeline,    │
│   regulatory submission layer — architecture is team choice) │
│                                                              │
│  Handles: trial balance, P&L, COSIF reports, PDD            │
│  calculation, accrual engine, tax engine, reconciliation     │
├──────────────────────────────────────────────────────────────┤
│  LEDGER                                                      │
│  Handles: immutable entries, account balances, event log,    │
│  idempotency, period guards, suspense accounts               │
└──────────────────────────────────────────────────────────────┘
```

**Applied to common financial features:**

| Feature | Where | Reason |
|---|---|---|
| Which clearing account to use (STR vs CIP-PIX) | Ledger | Determines the account at posting time |
| Suspense account for unallocated funds | Ledger | Money arrived — must be balanced immediately |
| Period guard (reject entries in closed periods) | Ledger | Must be enforced at the authoritative source |
| Tax entry (IOF debit/credit pair) | Ledger | The entry itself; calculation is upstream |
| IOF rate × base calculation | Upstream | Computed before posting, result sent as event |
| PDD provisioning calculation | Upstream | Risk classification → posts event to ledger |
| Trial balance | Upstream | Aggregation over existing ledger data |
| COSIF regulatory report | Upstream | Mapping + formatting over aggregated data |

The ledger does not calculate taxes, interest, provisions, or risk. It receives the results of those calculations as standard debit/credit events and records them.

---

## Data Model

### Schema

```sql
-- ============================================================
-- ENTITIES
-- Local registry of upstream entities. Populated from events.
-- entity_type is free-form metadata (e.g. 'merchant', 'customer') —
-- it is not a structural constraint and has no CHECK.
-- ============================================================
CREATE TABLE entities (
  id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  external_id      VARCHAR(255) NOT NULL,        -- ID in the upstream system (any format)
  name             VARCHAR(255),                 -- human-readable label
  parent_entity_id UUID         REFERENCES entities(id),  -- NULL = root; self-referencing FK for multi-level hierarchy
  is_active        BOOLEAN      DEFAULT true,
  metadata         JSONB,                        -- entity_type and any other attributes go here
  created_at       TIMESTAMP    DEFAULT NOW(),

  UNIQUE (external_id)
);

-- ============================================================
-- CHART OF ACCOUNTS
-- One set of accounts per entity, created from templates.
-- ============================================================
CREATE TABLE chart_of_accounts (
  id                UUID     PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_id         UUID     NOT NULL REFERENCES entities(id),

  code              VARCHAR(20)  NOT NULL,   -- e.g. '1.1.001'
  name              VARCHAR(255) NOT NULL,   -- e.g. 'Receivables'
  account_type      VARCHAR(20)  NOT NULL,   -- asset | liability | revenue | expense | equity
  category          VARCHAR(50),             -- structural classification hint for downstream reporting
                                             -- (e.g. 'current_assets', 'tax_liabilities', 'processing_fees')
                                             -- has no effect on posting behavior
  currency          CHAR(3)      NOT NULL DEFAULT 'BRL',  -- ISO 4217; each account holds one currency

  -- Incremental balance (Midaz-inspired)
  current_balance   DECIMAL(20,2) DEFAULT 0,
  balance_version   INTEGER       DEFAULT 0,
  last_entry_at     TIMESTAMP,

  parent_account_id UUID     REFERENCES chart_of_accounts(id),
  is_active         BOOLEAN  DEFAULT true,
  metadata          JSONB,
  created_at        TIMESTAMP DEFAULT NOW(),
  updated_at        TIMESTAMP DEFAULT NOW(),

  UNIQUE (entity_id, code),
  CHECK  (account_type IN ('asset', 'liability', 'revenue', 'expense', 'equity'))
);

-- ============================================================
-- TRANSACTIONS
-- Header grouping related entries into one atomic operation.
-- ============================================================
CREATE TABLE transactions (
  id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_id        UUID         NOT NULL REFERENCES entities(id),
  -- Accrual date (accrual basis date), not the posting date.
  -- A job running on 2026-01-02 posting yesterday's accrual sets effective_date = 2026-01-01.
  -- This is how the ledger supports accrual-basis accounting without any accrual logic of its own.
  effective_date   DATE         NOT NULL,

  transaction_type VARCHAR(50)  NOT NULL,                   -- 'sale', 'anticipation', 'settlement', 'accrual', 'tax_provision', ...
  -- pending  → entries exist but do NOT update current_balance (application skips balance update)
  -- committed → entries are balance-impacting; this is the default for most events
  -- voided   → only reachable from pending; status update only, no new entries posted,
  --            balance is unaffected because pending entries never touched it.
  --            Use for "never happened" cancellations before commit.
  --            For reversals of committed transactions, post a new transaction with reversing entries instead.
  status           VARCHAR(20)  DEFAULT 'committed',

  -- Reference to the originating event / object in the upstream system
  reference_id     VARCHAR(255) NOT NULL,
  reference_type   VARCHAR(50)  NOT NULL,

  description      TEXT,
  metadata         JSONB,

  idempotency_key  VARCHAR(255) UNIQUE NOT NULL,
  created_at       TIMESTAMP    DEFAULT NOW(),
  created_by       VARCHAR(100),

  CHECK (status IN ('pending', 'committed', 'voided'))
);

-- ============================================================
-- TRANSACTION ENTRIES
-- Individual debit/credit legs of a transaction.
-- ============================================================
CREATE TABLE transaction_entries (
  id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  transaction_id UUID         NOT NULL REFERENCES transactions(id) ON DELETE RESTRICT,
  account_id     UUID         NOT NULL REFERENCES chart_of_accounts(id),

  entry_type     VARCHAR(10)  NOT NULL,   -- 'debit' | 'credit'
  amount         DECIMAL(20,2) NOT NULL,
  currency       CHAR(3)      NOT NULL,   -- must match chart_of_accounts.currency for account_id (enforced by app)
  metadata       JSONB,
  created_at     TIMESTAMP    DEFAULT NOW(),

  CHECK (amount > 0),
  CHECK (entry_type IN ('debit', 'credit'))
);

-- ============================================================
-- EVENT LOG
-- Full audit trail of every inbound event.
-- ============================================================
CREATE TABLE event_log (
  id                  BIGSERIAL    PRIMARY KEY,
  event_type          VARCHAR(100) NOT NULL,
  event_id            VARCHAR(255) NOT NULL,  -- broker message ID (deduplication key)
  source              VARCHAR(50)  DEFAULT 'upstream',
  aggregate_id        UUID,
  aggregate_type      VARCHAR(50),
  payload             JSONB        NOT NULL,
  status              VARCHAR(20)  DEFAULT 'received', -- received | processing | processed | failed | skipped
  error_message       TEXT,
  transaction_id      UUID,
  -- Populated after processing. One element per entry posted.
  -- Provides a self-contained audit snapshot — no joins needed to understand what changed.
  -- Structure:
  -- [
  --   {
  --     "account_id":    "uuid",
  --     "account_code":  "1.1.001",
  --     "account_name":  "Receivables",
  --     "entry_type":    "debit" | "credit",
  --     "amount":        100.00,
  --     "balance_before": 0.00,
  --     "balance_after":  100.00
  --   }
  -- ]
  affected_accounts   JSONB,
  occurred_at         TIMESTAMP    DEFAULT NOW(),
  processed_at        TIMESTAMP,
  processing_time_ms  INTEGER,
  UNIQUE (event_id, event_type)
);

-- ============================================================
-- RECEIVABLES
-- Financial right (credit right) born from a sale event.
-- Tracks the lifecycle of the receivable from the ledger's perspective:
-- when it was created, its gross/net/fee breakdown, and when it settles.
--
-- Product-specific state (e.g. anticipation details, assignment chain)
-- belongs in the product service, which references receivables.id.
-- ============================================================
CREATE TABLE receivables (
  id                       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_id                UUID         NOT NULL REFERENCES entities(id),
  transaction_id           UUID         NOT NULL REFERENCES transactions(id),  -- originating sale transaction
  gross_amount             DECIMAL(20,2) NOT NULL,
  net_amount               DECIMAL(20,2) NOT NULL,
  fee_amount               DECIMAL(20,2) NOT NULL,
  status                   VARCHAR(50)  NOT NULL,  -- pending | settled | cancelled
  expected_settlement_date DATE,
  actual_settlement_date   DATE,
  created_at               TIMESTAMP    DEFAULT NOW(),
  updated_at               TIMESTAMP    DEFAULT NOW(),
  metadata                 JSONB
);

-- ============================================================
-- BALANCE SNAPSHOTS
-- Daily snapshots per account for historical queries.
-- ============================================================
CREATE TABLE account_balance_snapshots (
  id            UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id    UUID    NOT NULL REFERENCES chart_of_accounts(id),
  snapshot_date DATE    NOT NULL,
  balance       DECIMAL(20,2) NOT NULL,
  created_at    TIMESTAMP DEFAULT NOW(),
  UNIQUE (account_id, snapshot_date)
);

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX idx_entities_active   ON entities(id) WHERE is_active = true;
CREATE INDEX idx_entities_parent   ON entities(parent_entity_id) WHERE parent_entity_id IS NOT NULL;

CREATE INDEX idx_accounts_entity   ON chart_of_accounts(entity_id);
CREATE INDEX idx_accounts_code     ON chart_of_accounts(entity_id, code);
CREATE INDEX idx_accounts_type     ON chart_of_accounts(account_type);
CREATE INDEX idx_accounts_currency ON chart_of_accounts(entity_id, currency);
CREATE INDEX idx_accounts_active   ON chart_of_accounts(entity_id) WHERE is_active = true;

CREATE INDEX idx_txn_entity        ON transactions(entity_id, effective_date DESC);
CREATE INDEX idx_txn_status        ON transactions(status) WHERE status != 'committed';
CREATE INDEX idx_txn_reference     ON transactions(reference_type, reference_id);
CREATE INDEX idx_txn_type          ON transactions(transaction_type);
CREATE INDEX idx_txn_entity_date   ON transactions(entity_id, effective_date DESC, transaction_type);

CREATE INDEX idx_entry_txn         ON transaction_entries(transaction_id);
CREATE INDEX idx_entry_account     ON transaction_entries(account_id);
CREATE INDEX idx_entry_metadata    ON transaction_entries USING GIN (metadata);

CREATE INDEX idx_events_type       ON event_log(event_type, occurred_at DESC);
CREATE INDEX idx_events_status     ON event_log(status) WHERE status != 'processed';
CREATE INDEX idx_events_txn        ON event_log(transaction_id);
CREATE INDEX idx_events_aggregate  ON event_log(aggregate_type, aggregate_id);

CREATE INDEX idx_recv_entity       ON receivables(entity_id, status);
CREATE INDEX idx_recv_txn          ON receivables(transaction_id);
CREATE INDEX idx_recv_status       ON receivables(status, expected_settlement_date);

CREATE INDEX idx_snapshots_account ON account_balance_snapshots(account_id, snapshot_date DESC);

-- ============================================================
-- ACCOUNTING PERIODS
-- Controls which periods are open for posting.
-- The ledger rejects any transaction whose effective_date falls
-- in a closed or locked period. This is the authoritative guard
-- — period status is enforced at the source of truth, not in
-- upstream layers.
--
-- Status transitions:
--   open → closed  (normal month-end close)
--   closed → open  (authorized re-opening for corrections)
--   closed → locked (after regulatory submission — irreversible)
--   locked → *     (not allowed; corrections must be posted in
--                   the current open period as reversals)
-- ============================================================
CREATE TABLE accounting_periods (
  id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  period_date DATE         NOT NULL,   -- first day of the month: 2025-12-01 = December 2025
  status      VARCHAR(20)  NOT NULL DEFAULT 'open',
  opened_at   TIMESTAMP    DEFAULT NOW(),
  closed_at   TIMESTAMP,
  locked_at   TIMESTAMP,
  closed_by   VARCHAR(100),
  locked_by   VARCHAR(100),
  notes       TEXT,                    -- reason for re-opening or locking
  created_at  TIMESTAMP    DEFAULT NOW(),

  UNIQUE (period_date),
  CHECK (status IN ('open', 'closed', 'locked'))
);

CREATE INDEX idx_periods_status ON accounting_periods(status) WHERE status = 'open';
CREATE INDEX idx_periods_date   ON accounting_periods(period_date DESC);
```

---

## Receivables and the Product Service Boundary

A receivable (`receivables` table) is a **financial right** (credit right) — a first-class financial instrument that represents the merchant's right to receive a specific amount on a specific date. It is a legitimate ledger entity: it has identity, a gross/net/fee breakdown, and a settlement lifecycle (`pending → settled | cancelled`).

What the ledger does **not** model is how products operate on receivables. The anticipation product, for example, needs to track the anticipation rate, the number of days advanced, and the fee calculation formula. That state belongs in the **anticipation service**, which references `receivables.id` and posts entries to the ledger via events.

**Boundary rule:** if a field describes what happened to a receivable (settled on date X, cancelled by event Y), it belongs in the ledger. If it describes how a product processed it (anticipated at 1.5% for 20 days), it belongs in the product service.

```
Ledger (open-ledger)          Product service (e.g. anticipation-service)
─────────────────────         ──────────────────────────────────────────
receivables                   anticipations
  id ◄────────────────────────── receivable_id
  entity_id                     anticipation_id
  gross_amount                  anticipated_amount
  net_amount                    anticipation_fee
  fee_amount                    anticipation_rate
  status (pending|settled|      days_advanced
          cancelled)            anticipation_date
  expected_settlement_date      settled_at
  actual_settlement_date
```

The anticipation service posts two events to the ledger when it processes a receivable: one that moves the balance from `1.1.001 Receivables` to `1.1.002 Receivables Anticipated`, and one at settlement that clears `1.1.002` via World. The ledger records the entries; the product service owns the business state.

---

## Regulatory Mapping

Regulatory mapping (COSIF, FINREP, PCEC, etc.) is the responsibility of the **upstream reporting layer**, not the ledger. Applying our [layered architecture criterion](#10-layered-architecture--what-belongs-in-the-ledger): the COSIF code of an account is never needed at posting time — it is only needed when generating a regulatory report. That computation happens after the fact, over data already in the ledger.

The ledger uses free-form internal account codes (`1.1.001`, `3.1.001`, etc.) optimized for clarity and flexibility. The upstream regulatory reporting layer maintains the mapping from internal codes to framework codes, with its own versioning to handle updates over time.

### COSIF (Brazil)

Any institution regulated by the Banco Central do Brasil — IP, IFP, SCD, SEP, or bank — is required to use the **Plano Contábil das Instituições do Sistema Financeiro Nacional (COSIF)**. COSIF defines a mandatory hierarchical chart of accounts in the format `X.X.X.XX-D` (where D is a check digit). The upstream reporting layer translates ledger account codes to COSIF codes when submitting to the BACEN.

**Reference mapping — Merchant template (illustrative):**

| Internal code | Internal name           | COSIF code    | COSIF name (abbreviated)                          |
|---------------|-------------------------|---------------|---------------------------------------------------|
| 1.1.001       | Receivables             | 1.8.9.90-1    | Other Credits — Rights from Services Rendered     |
| 1.2.001       | Cash                    | 1.1.5.00-1    | Cash and Cash Equivalents — Bank Deposits          |
| 3.1.001       | Revenue - Sales         | 7.6.9.00-0    | Service Revenue — Other                           |
| 4.1.001       | Expense - MDR Fee       | 8.7.9.00-9    | Service Expenses — Other                       |

> **Important:** codes above are illustrative. Exact COSIF codes depend on entity type (IP vs. bank vs. SCD) and must be validated against the official BACEN publication.

### Other frameworks

The same upstream pattern applies to other regulatory frameworks:

| Framework | Regulator          | Applicable to                        |
|-----------|--------------------|--------------------------------------|
| `COSIF`   | BACEN (Brazil)     | IPs, IFPs, SCDs, SEPs, banks         |
| `FINREP`  | EBA (EU)           | EU credit institutions               |
| `PCEC`    | ACP (France)       | French credit institutions           |
| `GAAP`    | FASB (US)          | US entities (voluntary)              |

---

## Tax Accounting

The ledger **records** tax entries — it does not calculate them. Tax calculation (rate, base, applicable regime) is the responsibility of a dedicated tax service. The ledger receives the result as a standard debit/credit pair and posts it like any other entry.

### Boundary rule

| Responsibility | Owner |
|---|---|
| Calculate IOF rate × base × time factor | Tax service |
| Determine PIS/COFINS regime (cumulative vs. non-cumulative) | Tax service |
| Compute CSLL/IRPJ monthly estimate | Tax service |
| Post the resulting debit/credit entries | Ledger |
| Maintain tax liability balances | Ledger (via chart of accounts) |

### How tax entries reach the ledger

**IOF** — calculated per operation, posted atomically with the triggering transaction. The event handler calls the tax service before posting entries; the IOF entry is included in the same DB transaction:

| # | Account              | Type   | Amount | metadata                               |
|---|----------------------|--------|--------|----------------------------------------|
| 1 | 4.2.001 Expense - IOF | debit  | R$0.08 | `{"tax_type":"IOF","rate":0.000082}`  |
| 2 | 2.2.001 IOF Payable    | credit | R$0.08 | `{"triggers_transaction_id":"txn_123"}`|

**PIS/COFINS** — posted at month-end by a fiscal closing job as a dedicated `transaction_type: "tax_provision"` transaction.

**CSLL/IRPJ** — posted at quarter-end (with monthly estimates) by the same fiscal closing job.

### Tax accounts

Tax-related accounts follow the pattern below and are included in entity templates for regulated institutions:

| Code range | Nature | Examples |
|---|---|---|
| `2.2.xxx` | Tax liabilities (Payable / Provision) | IOF Payable, PIS/COFINS Payable, CSLL/IRPJ Provision |
| `4.2.xxx` | Tax expenses | Expense - IOF, Expense - PIS/COFINS, Expense - CSLL/IRPJ |

---

## Accrual Accounting

The ledger supports accrual-basis accounting natively — it does not implement it. The distinction matters:

- **The ledger provides:** `effective_date` (accrual basis date) on every transaction, immutable entries, and idempotency guarantees.
- **The ledger does not provide:** interest calculation, amortization schedules, day-count conventions, or any rule about when accrual should occur.

An external accrual engine (typically part of the credit product service) is responsible for determining how much revenue or expense accrued on a given day and posting it as a standard event. The ledger records the resulting entries.

### How accrual entries reach the ledger

The accrual job runs daily, computes each instrument's accrual, and posts one event per instrument with `effective_date` set to the accrual date — not the posting date. If the job runs at 01:00 on January 2nd for January 1st accruals, `effective_date = 2026-01-01` and `created_at = 2026-01-02T01:00:00Z`.

**Example — one day of interest accrual on a credit operation (R$10,000 at 2% p.m.):**

| # | Account                              | Type   | Amount  | metadata                                           |
|---|--------------------------------------|--------|---------|----------------------------------------------------|
| 1 | 1.3.001 Accrued Interest Receivable  | debit  | R$6.45  | `{"instrument_id":"loan_abc","accrual_date":"2026-01-01","rate":0.02,"days":1}` |
| 2 | 3.2.001 Revenue - Interest Income    | credit | R$6.45  | `{"method":"252_business_days"}`                   |

When cash arrives (interest payment):

| # | Account                                | Type   | Amount  |
|---|----------------------------------------|--------|---------|-
| 1 | 1.2.001 Cash                           | debit  | R$6.45  |
| 2 | 1.3.001 Accrued Interest Receivable    | credit | R$6.45  |

### Idempotency for periodic jobs

The `idempotency_key` on `transactions` prevents double-posting if the accrual job retries. The convention is:

```
accrual:{instrument_id}:{effective_date}
```

If the job runs twice for the same instrument and date, the second attempt hits the UNIQUE constraint on `idempotency_key` and is rejected — no duplicate entries.

### Accrual accounts

Entities running credit products should include these accounts in their chart:

| Code    | Name                          | Type      | Category          |
|---------|-------------------------------|-----------|-------------------|
| 1.3.001 | Accrued Interest Receivable   | asset     | accrued_revenue   |
| 2.3.001 | Deferred Revenue              | liability | deferred_revenue  |
| 3.2.001 | Revenue - Interest Income     | revenue   | financial_revenue |
| 3.2.002 | Revenue - Fee Income          | revenue   | financial_revenue |

> `Deferred Revenue` is used in discount operations where interest is received upfront and recognized daily over the instrument's life. `Accrued Interest Receivable` is used in post-paid interest models where the cash arrives later.

---

## PDD — Allowance for Doubtful Accounts

**Resolução CMN nº 2.682** requires financial institutions to classify every credit operation by risk level (AA through H) and maintain mandatory loss provisions against the credit portfolio. The provisioning percentages range from 0% (AA) to 100% (H).

Following the [layered architecture principle](#10-layered-architecture--what-belongs-in-the-ledger):

- **Upstream layer:** risk classification per operation (AA→H), computation of the required provision amount per rating band, decision to upgrade or downgrade a classification.
- **Ledger:** records the resulting provision entry (constitution or reversal) as a standard `transaction_type: "pdd_provision"` or `"pdd_reversal"` transaction.

### PDD entries

**Constituting a provision** (risk increased or new credit classified):

| # | Account                          | Type   | Amount   | metadata                                              |
|---|----------------------------------|--------|----------|-------------------------------------------------------|
| 1 | 4.3.001 Expense - PDD            | debit  | R$500.00 | `{"instrument_id":"loan_abc","rating":"D","rate":0.30}` |
| 2 | 1.6.002 PDD - Allowance          | credit | R$500.00 | `{"resolution":"CMN_2682"}`                           |

`1.6.002 PDD - Allowance` is a contra-asset (valuation allowance) — it carries a credit balance and is presented as a deduction from the credit portfolio on the balance sheet.

**Reversing a provision** (credit upgraded, paid off, or written off):

| # | Account                          | Type   | Amount   |
|---|----------------------------------|--------|----------|
| 1 | 1.6.002 PDD - Allowance          | debit  | R$500.00 |
| 2 | 4.3.001 Expense - PDD            | credit | R$500.00 |

### PDD accounts

Entities with credit portfolios should include these accounts:

| Code    | Name                  | Type    | Category          |
|---------|-----------------------|---------|-------------------|
| 1.6.001 | Credit Portfolio      | asset   | credit_operations |
| 1.6.002 | PDD - Allowance       | asset   | credit_operations |
| 4.3.001 | Expense - PDD         | expense | credit_expenses   |

> `1.6.002` uses `account_type: "asset"` with a permanent credit balance (net negative). This is the standard contra-asset treatment — the net credit portfolio value is `1.6.001 + 1.6.002`.

---

## Suspense Accounts

A suspense account holds funds that have arrived in the system but whose final allocation is not yet known. Unlike `pending` transactions — which represent events that may or may not happen — suspense entries represent money that **has arrived and must be balanced immediately**.

### Suspense vs. pending

| | `pending` transaction | Suspense account |
|---|---|---|
| Money in the system? | Not necessarily | Yes — funds received |
| Impacts `current_balance`? | No | Yes |
| Used when | Event may still be cancelled | Destination unknown or timing blocked |
| Resolved by | Committing or voiding the transaction | Posting a release entry to the correct account |

### When suspense accounts are used

- **Settlement window cutoff:** TED or COMPE funds arrive after the clearing window closes (STR closes at 17h30); the IP has the cash but cannot forward it until the next window.
- **Unidentified counterparty:** a PIX is received but the destination entity cannot be matched to any known account.
- **Amount mismatch:** funds received don't match the expected settlement instruction; held until reconciliation confirms the correct allocation.

The decision to move funds out of suspense — matching, reconciling, identifying the counterparty — belongs in the upstream layer. The act of recording that funds arrived and are awaiting allocation belongs in the ledger.

### Suspense account convention

The `9.8.xxx` range is reserved for suspense accounts, one per clearing modality:

| Code    | Name                | Used when                                  |
|---------|---------------------|--------------------------------------------|
| 9.8.001 | Suspense/STR        | TED/large-value wires outside STR window   |
| 9.8.002 | Suspense/CIP-PIX    | PIX with unidentified destination           |
| 9.8.003 | Suspense/COMPE      | Cheque float pending COMPE clearance       |

### Suspense entries

**Capturing funds into suspense** (TED received, STR window closed, destination unknown):

| # | Account                    | Type   | Amount      | metadata                                           |
|---|----------------------------|--------|-------------|----------------------------------------------------|
| 1 | 1.2.001 Cash               | debit  | R$100,000   | `{"bank_ref":"TED_98765","received_at":"17:35"}` |
| 2 | 9.8.001 Suspense/STR       | credit | R$100,000   | `{"reason":"post_cutoff","window_reopens":"next_business_day"}` |

**Releasing from suspense** (next business day, destination identified):

| # | Account                    | Type   | Amount      |
|---|----------------------------|--------|-------------|
| 1 | 9.8.001 Suspense/STR       | debit  | R$100,000   |
| 2 | [entity's target account]  | credit | R$100,000   |

The `idempotency_key` convention for suspense releases is `suspense_release:{bank_ref}` to prevent double-allocation if the upstream reconciliation job retries.

---

## Period Closing

### What belongs in the ledger

The ledger owns the **period guard**: any transaction whose `effective_date` falls in a closed or locked period is rejected at posting time. This must be enforced at the authoritative source — an upstream layer cannot substitute for this check.

The ledger also **records** closing entries (e.g. zeroing revenue and expense accounts into Net Income / Retained Earnings) when they are posted as standard `transaction_type: "period_closing"` events. It does not calculate them.

### What belongs in the upstream layer

The upstream layer is responsible for:
- Computing the trial balance for the period
- Determining the net result (revenues − expenses)
- Generating and posting closing entry events to the ledger
- Producing P&L statements and balance sheets from ledger data
- Submitting regulatory reports (COSIF/BACEN) after the period is locked

### Period status transitions

```
open ──month-end close──▶ closed ──regulatory submission──▶ locked
         ▲                   │
         └──re-open (auth)───┘
         (locked periods cannot be re-opened;
          corrections must be posted in the current open period)
```

| Status   | New entries allowed? | Can be re-opened? |
|----------|----------------------|-------------------|
| `open`   | Yes                  | N/A               |
| `closed` | No                   | Yes (authorized)  |
| `locked` | No                   | No                |

### Corrections in closed periods

Once a period is closed, corrections to entries within it must be posted in the **current open period** as reversing transactions (`transaction_type: "reversal"`) with `effective_date` set to today. Backdating to the closed period is not allowed.

Once a period is **locked** (regulatory submission made), this is permanent and irreversible. The same correction rule applies, with the additional requirement that the reversal rationale must be captured in `transactions.description` for audit purposes.

### Closing entry example

The upstream layer calculates net result for December 2025 (Revenue R$500k − Expenses R$320k = R$180k) and posts:

| # | Account                         | Type   | Amount      |
|---|---------------------------------|--------|-------------|
| 1 | 3.1.001 Revenue - Sales         | debit  | R$500,000   |
| 2 | 4.1.001 Expense - MDR Fee       | credit | R$320,000   |
| 3 | 2.4.001 Net Income / Retained Earnings | credit | R$180,000   |

`effective_date = 2025-12-31`, `transaction_type = "period_closing"`, `idempotency_key = "period_closing:2025-12"`.

---

## Chart of Accounts

The Chart of Accounts is the set of accounts belonging to a single entity. It is fully flexible: an entity can have any number of accounts, with any names and types that fit its financial reality. There is no enforced structure — a simple entity might have three accounts; a complex one might have dozens.

A **template** is a pre-defined Chart of Accounts used as a starting point when registering a new entity. Templates are a convenience, not a constraint. You can apply one as-is, extend it, or build a chart from scratch.

The five account types available are `asset`, `liability`, `revenue`, `expense`, and `equity`. The account code (e.g. `1.1.001`) is free-form — use any numbering convention that makes sense for your system.

### Reference Template: Merchant

This template is used as the reference entity in all transaction flow examples below.

| Code    | Name                       | Type      | Category            | Currency |
|---------|----------------------------|-----------|---------------------|----------|
| 1.1.001 | Receivables                | asset     | current_assets      | BRL      |
| 1.1.002 | Receivables Anticipated    | asset     | current_assets      | BRL      |
| 1.2.001 | Cash                       | asset     | cash                | BRL      |
| 2.2.001 | IOF Payable                | liability | tax_liabilities     | BRL      |
| 2.2.002 | PIS/COFINS Payable         | liability | tax_liabilities     | BRL      |
| 2.2.003 | CSLL/IRPJ Provision        | liability | tax_liabilities     | BRL      |
| 3.1.001 | Revenue - Sales            | revenue   | operating_revenue   | BRL      |
| 4.1.001 | Expense - MDR Fee          | expense   | processing_fees     | BRL      |
| 4.1.002 | Expense - Platform Fee     | expense   | platform_fees       | BRL      |
| 4.1.003 | Expense - Anticipation Fee | expense   | financial_fees      | BRL      |
| 4.2.001 | Expense - IOF              | expense   | tax_expenses        | BRL      |
| 4.2.002 | Expense - PIS/COFINS       | expense   | tax_expenses        | BRL      |
| 4.2.003 | Expense - CSLL/IRPJ        | expense   | tax_expenses        | BRL      |
| 9.9.998 | Transfer                   | equity    | internal            | BRL      |
| 9.9.999 | World                      | equity    | external            | BRL      |

> For merchants operating in multiple currencies, provision one set of accounts per currency (e.g. `1.1.001/BRL` and `1.1.001/USD`). The account code convention is free-form — use whatever naming makes sense for your system.

### Reference Template: Customer

A simpler chart for an entity that primarily incurs payables. Included to illustrate that the same ledger can serve both sides of a transaction with completely different account structures.

| Code    | Name                    | Type      | Category            | Currency |
|---------|-------------------------|-----------|---------------------|----------|
| 2.1.001 | Payable to Counterparty | liability | current_liabilities | BRL      |
| 4.1.001 | Expense - Purchases     | expense   | cost_of_goods       | BRL      |
| 9.9.998 | Transfer                | equity    | internal            | BRL      |
| 9.9.999 | World                   | equity    | external            | BRL      |

### Reference Template: Operator

For white-label operators (Company B level in a payfac hierarchy). Collects platform fees from sub-merchants and pays a white-label fee upstream to the root platform.

| Code    | Name                       | Type    | Category          | Currency |
|---------|----------------------------|---------|-------------------|----------|
| 1.1.001 | Receivables                | asset   | current_assets    | BRL      |
| 3.1.001 | Revenue - Platform Fee     | revenue | operating_revenue | BRL      |
| 4.1.001 | Expense - White-label Fee  | expense | platform_fees     | BRL      |
| 9.9.998 | Transfer                   | equity  | internal          | BRL      |
| 9.9.999 | World                      | equity  | external          | BRL      |

### Reference Template: Platform

For the root platform entity (Fintech A level). Receives both direct platform fees (from merchants it owns directly) and white-label fees (from operators below it).

| Code    | Name                       | Type    | Category          | Currency |
|---------|----------------------------|---------|-------------------|----------|
| 1.1.001 | Receivables                | asset   | current_assets    | BRL      |
| 3.1.001 | Revenue - Platform Fee     | revenue | operating_revenue | BRL      |
| 3.1.002 | Revenue - White-label Fee  | revenue | operating_revenue | BRL      |
| 9.9.998 | Transfer                   | equity  | internal          | BRL      |
| 9.9.999 | World                      | equity  | external          | BRL      |

### Reference Template: BaaS Customer

For end-users of a Banking-as-a-Service product (digital account holders). The checking account is an asset from the customer's perspective; the BaaS owes the balance to the customer.

| Code    | Name             | Type  | Category       | Currency |
|---------|------------------|-------|----------------|----------|
| 1.1.001 | Checking Account | asset | current_assets | BRL      |
| 1.1.002 | Savings Account  | asset | current_assets | BRL      |
| 9.9.998 | Transfer         | equity| internal       | BRL      |
| 9.9.999 | World            | equity| external       | BRL      |

### System Boundary Accounts

The `9.9.xxx` range is reserved for system boundary accounts. `9.9.999 World` and `9.9.998 Transfer` are created for every entity. For operational deployments, `World` should be sub-typed by clearing counterparty (see [Core Principle 5](#5-system-boundary-accounts-formance)).

| Event                          | Debit            | Credit           |
|--------------------------------|------------------|------------------|
| Deposit via PIX                | Checking         | World/CIP-PIX    |
| Deposit via TED                | Checking         | World/STR        |
| Withdrawal via PIX             | World/CIP-PIX    | Checking         |
| Withdrawal via TED             | World/STR        | Checking         |
| Internal transfer — sender     | Transfer         | Checking         |
| Internal transfer — receiver   | Checking         | Transfer         |
| Chargeback (money returns)     | Checking         | World/CIP-PIX    |
| Settlement / bank payout       | World/Bank-{n}   | Receivables      |

**Tracing money across the system:**

```
External bank ──deposit──▶ [World ▶ Checking]  entity A
                                     │
                           [Transfer ▶ Transfer]  A → B (internal)
                                                │
                                   [Checking ▶ World] ──withdrawal──▶ External bank
```

Every real entering the ledger via World must eventually leave via World (or remain as a balance). Every Transfer debit on one entity has an exact Transfer credit on another. The full journey of every unit of currency is traceable without joins to external systems.

---

## Transaction Flows

All monetary values below use USD for clarity. The same patterns apply to any currency.

### Example 1 — Sale ($100.00, MDR 2%, platform fee 0.3%)

> **MDR (Merchant Discount Rate):** the fee charged by a payment acquirer on each card transaction.

**Inbound event:**
```json
{
  "event_type": "transaction.created",
  "event_id": "evt_001",
  "timestamp": "2025-12-10T10:00:00Z",
  "data": {
    "transaction_id": "txn_123",
    "entity_id": "abc-123",
    "gross_amount": 100.00,
    "mdr_rate": 0.02,
    "platform_fee_rate": 0.003,
    "expected_settlement_date": "2025-12-30"
  }
}
```

**Entries posted (6 balanced legs):**

| # | Account                     | Type   | Amount  | Key metadata                       |
|---|-----------------------------|--------|---------|------------------------------------|
| 1 | 1.1.001 Receivables         | debit  | $100.00 | transaction_id: txn_123            |
| 2 | 3.1.001 Revenue - Sales     | credit | $100.00 | transaction_id: txn_123            |
| 3 | 4.1.001 Expense - MDR       | debit  |   $2.00 | mdr_rate: 0.02, formula: "100×0.02"|
| 4 | 1.1.001 Receivables         | credit |   $2.00 | —                                  |
| 5 | 4.1.002 Expense - Platform  | debit  |   $0.30 | platform_fee_rate: 0.003           |
| 6 | 1.1.001 Receivables         | credit |   $0.30 | —                                  |

> **Balance check:** $102.30 total debits = $102.30 total credits ✓  
> **Result:** Merchant has $97.70 in Receivables.

---

### Example 2 — Early Payment / Anticipation

**Scenario:** Merchant has $97.70 due on 2025-12-30 and requests early payment on 2025-12-10. Anticipation fee: 1.5% = $1.47.

**Inbound event:**
```json
{
  "event_type": "anticipation.created",
  "event_id": "evt_002",
  "data": {
    "anticipation_id": "ant_456",
    "entity_id": "abc-123",
    "receivable_amount": 97.70,
    "anticipation_rate": 0.015,
    "anticipation_fee": 1.47,
    "net_amount": 96.23,
    "days_advanced": 20,
    "original_settlement_date": "2025-12-30"
  }
}
```

**Entries posted:**

| # | Account                            | Type   | Amount  | Key metadata                         |
|---|------------------------------------|--------|---------|--------------------------------------|
| 1 | 1.1.002 Receivables Anticipated    | debit  | $97.70  | anticipation_id: ant_456             |
| 2 | 1.1.001 Receivables                | credit | $97.70  | original_settlement_date: 2025-12-30 |
| 3 | 4.1.003 Expense - Anticipation Fee | debit  |  $1.47  | rate: 0.015, days_advanced: 20       |
| 4 | 1.1.002 Receivables Anticipated    | credit |  $1.47  | formula: "97.70 × 0.015"             |

> **Result:** Merchant has $96.23 in Receivables Anticipated.

---

### Example 3 — Settlement (with World Account)

**Scenario:** The anticipated amount is settled — cash transferred to the merchant's bank account and leaves the system.

**Inbound event:**
```json
{
  "event_type": "settlement.completed",
  "event_id": "evt_003",
  "data": {
    "settlement_id": "settle_789",
    "entity_id": "abc-123",
    "amount": 96.23,
    "settlement_date": "2025-12-10",
    "bank_reference": "WIRE_12345"
  }
}
```

**Entries posted:**

| # | Account                            | Type   | Amount  | Key metadata                        |
|---|------------------------------------|--------|---------|-------------------------------------|
| 1 | 9.9.999 World                      | debit  | $96.23  | bank_reference: WIRE_12345          |
| 2 | 1.1.002 Receivables Anticipated    | credit | $96.23  | settlement_date: 2025-12-10         |

> **Balance check:** $96.23 total debits = $96.23 total credits ✓  
> **Result:** Receivables Anticipated is cleared. World account shows $96.23 leaving the system.

---

### Example 4 — Reversal

A reversal undoes a `committed` transaction by posting a new transaction with mirror entries. The ledger does not model *why* the reversal happened — chargeback, refund, error correction — that is upstream business logic captured in `metadata`. The ledger's only concern is that every entry from the original transaction is offset.

> This example assumes the sale from Example 1 has not yet been settled (Receivables = $97.70). For post-settlement reversals, the same entries apply but accounts like World need to reflect funds returning from the external system.

**Inbound event:**
```json
{
  "event_type": "transaction.reversed",
  "event_id": "evt_004",
  "data": {
    "reversal_id": "rev_999",
    "transaction_id": "txn_123",
    "entity_id": "abc-123",
    "reason": "chargeback",
    "amount": 100.00
  }
}
```

**Entries posted (mirror of Example 1):**

| # | Account                     | Type   | Amount  | Key metadata                              |
|---|-----------------------------|--------|---------|-------------------------------------------|
| 1 | 3.1.001 Revenue - Sales     | debit  | $100.00 | reversal_id: rev_999, reason: chargeback  |
| 2 | 1.1.001 Receivables         | credit | $100.00 | —                                         |
| 3 | 1.1.001 Receivables         | debit  |   $2.00 | reversal: mdr_fee                         |
| 4 | 4.1.001 Expense - MDR       | credit |   $2.00 | —                                         |
| 5 | 1.1.001 Receivables         | debit  |   $0.30 | reversal: platform_fee                    |
| 6 | 4.1.002 Expense - Platform  | credit |   $0.30 | —                                         |

> **Balance check:** $102.30 total debits = $102.30 total credits ✓  
> **Result:** All accounts return to $0. Revenue, MDR, and platform fee entries are fully offset.

---

## Balance Strategy

### Hybrid approach _(Midaz-inspired)_

| Layer                     | How it works                                                               | Purpose                          |
|---------------------------|----------------------------------------------------------------------------|----------------------------------|
| **Incremental balance**   | Application updates `current_balance` within the same DB transaction      | Instant reads (< 5ms)            |
| **Nightly recalculation** | Background job sums all entries per account, compares to `current_balance` | Consistency validation           |
| **Daily snapshot**        | Job snapshots all account balances at 2 AM UTC                             | Historical queries / time-travel |

### Application-managed balance update

`current_balance` is maintained by the application, not a database trigger. All balance updates happen inside the same database transaction that inserts the entries — if anything fails, the whole operation rolls back atomically.

Before committing, the application validates double-entry per currency:

```python
from collections import defaultdict

def validate_double_entry(entries):
    totals = defaultdict(lambda: Decimal('0'))
    for entry in entries:
        sign = 1 if entry.entry_type == 'debit' else -1
        totals[entry.currency] += sign * entry.amount
    for currency, net in totals.items():
        if net != 0:
            raise ValueError(f"Double-entry imbalance in {currency}: {net}")
```

For each entry being posted, the application must:
1. `SELECT ... FOR UPDATE` the affected account row (acquires a row-level lock, serializing concurrent writes to the same account)
2. Compute the delta using the formula below
3. `UPDATE current_balance` and increment `balance_version`

```python
# pseudocode — runs inside the same DB transaction as entry inserts
for entry in entries:
    account = session.execute(
        select(Account)
        .where(Account.id == entry.account_id)
        .with_for_update()           # row-level lock
    ).scalar_one()

    delta = entry.amount if is_normal_side(account.account_type, entry.entry_type) else -entry.amount

    account.current_balance += delta
    account.balance_version += 1
    account.last_entry_at = now()
```

`balance_version` is a change counter — incremented on every balance update. The nightly validation job uses it to detect accounts that were modified outside the expected flow.

### Balance formula by account type

| Account type                       | Normal (increasing) side | Formula                   |
|------------------------------------|--------------------------|---------------------------|
| `asset` / `expense`                | debit                    | Σ debits − Σ credits      |
| `liability` / `revenue` / `equity` | credit                   | Σ credits − Σ debits      |

`pending` transactions **never** update `current_balance` — the balance update is skipped entirely until the transaction is committed.

### Performance targets

| Operation            | Target  |
|----------------------|---------|
| Balance read         | < 5ms   |
| Monthly statement    | < 500ms |
| Full balance sheet   | < 1s    |

---

## Statement API

The statement is a formatted view over the entries for a given entity and date range.

```json
{
  "entity_id": "abc-123",
  "period": {
    "start_date": "2025-12-01",
    "end_date": "2025-12-31"
  },
  "summary": {
    "opening_balance": 0.00,
    "total_in": 100.00,
    "total_out": 3.77,
    "closing_balance": 96.23
  },
  "entries": [
    {
      "date": "2025-12-10",
      "transaction_id": "txn_ledger_001",
      "type": "sale",
      "description": "Sale #txn_123",
      "movements": [
        { "account": "Receivables",    "entry_type": "debit",  "amount": 100.00 },
        { "account": "Revenue - Sales","entry_type": "credit", "amount": 100.00 }
      ],
      "balance_after": 100.00
    }
  ]
}
```

Generation logic:
1. **Opening balance** — `current_balance` or snapshot from day before the period start.
2. **Movements** — all entries in the date range, ordered by `created_at`.
3. **Running balance** — accumulated per movement.

---

## Event-Driven Architecture

```
┌──────────────────┐
│  UPSTREAM SVC    │
│  Processes op.   │
│  Saves to own DB │
└────────┬─────────┘
         │ publishes event
         ▼
┌──────────────────┐
│  MESSAGE BROKER  │
│  (Kafka / SQS)   │
└────────┬─────────┘
         │ consumed by
         ▼
┌──────────────────────────┐
│      LEDGER SERVICE      │
│  1. Write to event_log   │
│  2. Create transaction   │
│  3. Post entries         │
│  4. App updates balance  │
└──────────────────────────┘
```

### Entity registration and account provisioning

Entity registration and account creation are **separate concerns**. An entity can exist in the ledger with no accounts — accounts are provisioned explicitly, either at registration time or later as the entity's needs evolve.

The `entity.created` event supports three modes:

**Option A — template shortcut** (recommended for standard cases)
```json
{
  "event_type": "entity.created",
  "data": {
    "entity_id": "abc-123",
    "name": "ACME Store",
    "parent_entity_id": "fintech-a",
    "template": "merchant"
  }
}
```
The ledger applies the named template and creates all accounts defined in it.

**Option B — inline accounts** (for custom structures)
```json
{
  "event_type": "entity.created",
  "data": {
    "entity_id": "abc-123",
    "name": "ACME Store",
    "accounts": [
      { "code": "1.1.001", "name": "Receivables",  "account_type": "asset"  },
      { "code": "9.9.999", "name": "World",         "account_type": "equity" }
    ]
  }
}
```

**Option C — register only, add accounts later**
```json
{
  "event_type": "entity.created",
  "data": { "entity_id": "abc-123", "name": "ACME Store" }
}
```
The entity is registered with no accounts. A subsequent `accounts.created` event adds them. This supports entities whose account structure is not known at registration time, or that evolve over time (e.g. a merchant that enables anticipation later gets `Receivables Anticipated` added without re-registering).

If a financial event arrives for an entity with no matching account, the handler must reject it with a clear error — never auto-create accounts implicitly.

### Entity hierarchy and fee cascade

Entities form a tree via `parent_entity_id`. Depth is arbitrary. `NULL` = root (the platform itself).

```
fintech-a          (parent = NULL)       ← root
├── merchant-direct (parent = fintech-a) ← direct merchant, no operator
├── company-b       (parent = fintech-a) ← white-label operator
│   ├── merchant-b1 (parent = company-b)
│   └── merchant-b2 (parent = company-b)
└── company-c       (parent = fintech-a)
    └── merchant-c1 (parent = company-c)
```

**Fee cascade rule:** when processing a transaction for a merchant, the handler walks up `parent_entity_id` until `NULL`, creating one ledger transaction per ancestor that has a fee agreement with the child. The ledger does not enforce fee rules — that is application logic driven by the entity tree.

**Querying the full tree** (recursive CTE):

```sql
WITH RECURSIVE entity_tree AS (
  -- anchor: start from any node
  SELECT id, name, parent_entity_id, 0 AS depth
  FROM entities
  WHERE id = :root_id

  UNION ALL

  -- recursion: descend one level per iteration
  SELECT e.id, e.name, e.parent_entity_id, et.depth + 1
  FROM entities e
  JOIN entity_tree et ON e.parent_entity_id = et.id
)
SELECT * FROM entity_tree ORDER BY depth;
```

### Processing flow

1. Upstream service publishes event with full payload.
2. Ledger writes the raw event to `event_log` with `status = received`.
3. Handler looks up the entity using `event.data.entity_id` → `entities.external_id`; if not found, registers it.
4. Handler creates the `transaction` header.
5. Handler inserts all `entries` in a single atomic operation.
6. Application updates `current_balance` on each affected account via `SELECT FOR UPDATE` within the same transaction.
7. Handler updates `receivables` if applicable.
8. Handler marks `event_log` row as `processed`.
9. On failure: marks `failed`, event is retried with exponential backoff.

### Supported event types

| Event                   | Trigger                            | Ledger action                                        |
|-------------------------|------------------------------------|------------------------------------------------------|
| `entity.created`        | New entity registered upstream     | Register entity; optionally provision accounts       |
| `accounts.created`      | Accounts added to existing entity  | Create accounts from template or inline definition   |
| `transaction.created`   | New sale                           | Post sale + fee entries                              |
| `anticipation.created`  | Early payment request              | Reclassify receivable + post anticipation fee        |
| `settlement.completed`  | Funds disbursed                    | Post World debit + Receivables credit                |
| `deposit.created`       | Money enters from external bank    | Post World credit + Checking debit                   |
| `withdrawal.created`    | Money leaves to external bank      | Post Checking credit + World debit                   |
| `transfer.created`      | Internal transfer between entities | Post Transfer+Checking on sender; Checking+Transfer on receiver — two linked transactions, one DB commit |
| `transaction.voided`    | Cancelled before commit            | Set status → `voided`; no entries posted; balance unchanged |
| `transaction.reversed`  | Post-commit reversal (any reason)  | Post new transaction with mirror entries             |

### Idempotency

There are two independent deduplication mechanisms with different scopes:

| Mechanism | Table | Scope | Protects against |
|---|---|---|---|
| `UNIQUE (event_id, event_type)` | `event_log` | Message level | Broker delivering the same message twice |
| `UNIQUE (idempotency_key)` | `transactions` | Business operation level | Upstream retrying with a new message ID for the same operation |

The two layers are necessary because `event_log` deduplication only catches the exact same message arriving twice. If the upstream re-publishes the same business operation with a new `event_id` (e.g. a retry that generates a new broker message), `event_log` lets it through — `idempotency_key` is the last line of defence.

**Generating `idempotency_key`**

The key must be derived from the business data, not from `event_id`:

```
idempotency_key = "{transaction_type}:{reference_id}"
```

Examples:
- `"sale:txn_123"`
- `"anticipation:ant_456"`
- `"settlement:settle_789"`

This guarantees that no matter how many events arrive for the same upstream operation, only one ledger transaction is ever created.

---

## Multi-Currency

### Rules

1. Each account holds exactly one currency (`chart_of_accounts.currency`).
2. Each entry records its currency (`transaction_entries.currency`).
3. Application enforces: `entry.currency == account.currency`. Posting a USD entry to a BRL account is rejected.
4. Double-entry is validated per currency, not globally.

### FX conversion pattern

A currency conversion uses two single-currency **FX transit accounts** as intermediaries. Each transit account is denominated in one currency and must net to zero after every completed conversion cycle.

**Example:** customer converts $100.00 USD → BRL at rate 5.20.

Accounts provisioned for the entity:
| Code    | Name              | Type   | Currency |
|---------|-------------------|--------|----------|
| 1.1.010 | Receivables       | asset  | USD      |
| 1.1.011 | Receivables       | asset  | BRL      |
| 5.1.001 | FX Transit        | equity | USD      |
| 5.1.002 | FX Transit        | equity | BRL      |

**Transaction 1 — USD side** (closes the USD position):

| # | Account           | Type   | Amount       | Key metadata                  |
|---|-------------------|--------|--------------|-------------------------------|
| 1 | 1.1.010 Recv USD  | credit | $100.00 USD  | fx_rate: 5.20, pair: BRL      |
| 2 | 5.1.001 FX-USD    | debit  | $100.00 USD  | conversion_id: conv_001       |

> USD double-entry: $100 debits = $100 credits ✓

**Transaction 2 — BRL side** (opens the BRL position):

| # | Account           | Type   | Amount        | Key metadata                  |
|---|-------------------|--------|---------------|-------------------------------|
| 1 | 5.1.002 FX-BRL    | credit | R$520.00 BRL  | conversion_id: conv_001       |
| 2 | 1.1.011 Recv BRL  | debit  | R$520.00 BRL  | fx_rate: 5.20, pair: USD      |

> BRL double-entry: R$520 debits = R$520 credits ✓

After both transactions, FX Transit accounts net to zero (USD: $100 debit cancelled by credit; BRL: R$520 credit cancelled by debit). The exchange rate and formula are stored in `metadata` — never recomputed.

### FX gain / loss

If the conversion rate differs from the rate at which the original obligation was recorded (e.g. an invoice priced at one rate, settled at another), the difference is posted to dedicated gain/loss accounts:

| Code    | Name            | Type    | Currency |
|---------|-----------------|---------|----------|
| 3.2.001 | FX Gain         | revenue | BRL      |
| 4.2.001 | FX Loss         | expense | BRL      |

The gain/loss entry is added as an extra leg to Transaction 2, keeping the BRL side balanced.

---

## Rounding

All monetary calculations use **HALF_UP rounding to 2 decimal places**, applied independently per currency.

- `$97.70 × 0.015 = $1.4655` → rounds to **`$1.47`**
- This is the standard used by payment processors (Stripe, Adyen) and is the most auditable rule: any value ending in 5 always rounds up, with no exceptions.
- HALF_EVEN (banker's rounding) was considered but rejected — it produces counter-intuitive results (`$1.4655 → $1.46`) that are hard to explain to users and auditors.
- For currencies with no decimal places (e.g. JPY), use `Decimal('1')` as the precision constant instead of `Decimal('0.01')`.

**In Python**, always use `decimal.Decimal` — never `float`. Floating-point arithmetic is binary and cannot represent most decimal fractions exactly (`0.1 + 0.2 = 0.30000000000000004`), which breaks double-entry balance checks at scale.

```python
from decimal import Decimal, ROUND_HALF_UP

PRECISION = Decimal('0.01')

def round_amount(value: Decimal) -> Decimal:
    return value.quantize(PRECISION, rounding=ROUND_HALF_UP)
```

---

## Technical Requirements

- **PostgreSQL 13+** — JSONB, GIN indexes, `gen_random_uuid()`
- **Message broker** — Kafka, RabbitMQ, or SNS+SQS
- **Redis** — optional, recommended for hot balance caching
- **PgBouncer** — connection pooling for high-throughput writes

---

## Testing Strategy

### Unit tests (100% coverage required)
- Debit/credit balance validation per transaction
- Balance formula correctness per account type
- `current_balance` application-managed update behaviour
- Idempotency on duplicate events
- World account entry generation

### Integration tests
- Full flow: sale → settlement (with World account)
- Early payment flow
- Cancellation / chargeback reversal
- Event replay (reprocess a `failed` event)
- Multi-leg transactions

### Load tests
- 1,000 transactions/second with multiple entries each
- Balance read with 1M+ entries in account history
- Monthly statement with 10K+ movements
- Nightly validation across 100K+ accounts

---

## References

- [Accounting for Computer Scientists — Martin Kleppmann](https://martin.kleppmann.com/2011/03/07/accounting-for-computer-scientists.html)
- [Event Sourcing — Martin Fowler](https://martinfowler.com/eaaDev/EventSourcing.html)
- [Midaz Ledger](https://github.com/LerianStudio/midaz) — transaction model, incremental balance strategy
- [Formance Ledger](https://www.formance.com/) — World account, event sourcing, rich metadata
- [Modern Treasury — What is a ledger database?](https://www.moderntreasury.com/learn/what-is-a-ledger-database)
- [Double-Entry Bookkeeping — Wikipedia](https://en.wikipedia.org/wiki/Double-entry_bookkeeping)
