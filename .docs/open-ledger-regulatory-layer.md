# Open Ledger — Regulatory & Compliance Layer Guide

---

## Overview

The ledger is the authoritative source of immutable financial entries. It does not calculate taxes, classify credit risk, map to COSIF codes, or generate regulatory reports. Those responsibilities belong to the **upstream layer** — whether a data warehouse, an analytical pipeline, a reporting service, or any architecture a team chooses.

This document is a practical guide for building that upstream layer. Each section describes:
- What data to read from the ledger
- How to compute the regulatory requirement
- How to post the result back to the ledger (when applicable)

```
┌──────────────────────────────────────────────────────────────────┐
│  UPSTREAM LAYER (this document)                                  │
│                                                                  │
│  COSIF mapping · Trial balance · PDD · Accrual engine           │
│  Tax engine (IOF, PIS/COFINS, CSLL/IRPJ) · Period closing       │
│                                                    │             │
│                            events (debit/credit) ◄┘             │
├──────────────────────────────────────────────────────────────────┤
│  LEDGER (open-ledger)                                            │
│                                                                  │
│  entities · chart_of_accounts · transactions                    │
│  transaction_entries · event_log · receivables                  │
│  account_balance_snapshots · accounting_periods                  │
└──────────────────────────────────────────────────────────────────┘
```

The pattern is always the same:

1. **Read** account balances or entries from the ledger
2. **Compute** the regulatory requirement (outside the ledger)
3. **Post** the result back as a standard event with a `transaction_type` that identifies its nature

---

## Portability

Open-ledger was conceived with the **Brazilian regulatory framework** as its primary reference: COSIF for the chart of accounts, Resolução CMN nº 2.682 for credit provisioning, and IOF/PIS/COFINS/CSLL/IRPJ for tax accounting. Brazil was chosen because it is one of the most demanding regulatory environments for payment institutions globally — if the architecture holds here, it holds anywhere.

The ledger itself, however, has no knowledge of any of this. It records debits and credits against accounts identified by free-form codes. It does not know what COSIF is, what PDD means, or that IOF exists. **All regulatory logic lives in the upstream layer.**

This separation is what makes the architecture portable. Replacing Brazilian regulations with EU, US, or UK equivalents is a matter of implementing a different upstream layer — the ledger schema, posting flow, and invariants remain identical.

| Concern | Brazil | EU | USA | UK |
|---|---|---|---|---|
| Chart of accounts mapping | COSIF (BACEN) | FINREP (EBA) | Call Reports (FFIEC) | PRA reporting |
| Credit loss provisioning | PDD — Res. CMN 2.682 | ECL — IFRS 9 | CECL — ASC 326 | ECL — IFRS 9 |
| Indirect tax on operations | IOF | VAT on financial services | (varies by state) | Stamp Duty |
| Revenue tax | PIS/COFINS | VAT | Sales tax (indirect) | VAT |
| Profit tax provision | CSLL / IRPJ | Corporate tax (national) | Federal income tax | Corporation tax |

See [Section 7](#7-adapting-to-other-regulatory-frameworks) for implementation notes per jurisdiction.

---

## 1. COSIF Mapping

### What it is

The **Plano Contábil das Instituições do Sistema Financeiro Nacional (COSIF)** is the mandatory chart of accounts for all financial institutions regulated by the Banco Central do Brasil. Every balance sheet submitted to the BACEN must use COSIF codes in the format `X.X.X.XX-D`.

The ledger uses free-form internal codes (`1.1.001`, `3.1.001`, etc.). The upstream layer maintains the mapping table and applies it when generating regulatory reports.

### Where the mapping lives

The upstream layer owns a mapping table (outside the ledger database):

```sql
-- In the upstream layer's database, not in the ledger
CREATE TABLE cosif_account_mappings (
  entity_type      VARCHAR(50)  NOT NULL,  -- 'IP', 'SCD', 'bank', etc.
  internal_code    VARCHAR(20)  NOT NULL,  -- matches chart_of_accounts.code
  cosif_code       VARCHAR(20)  NOT NULL,  -- e.g. '1.8.9.90-1'
  cosif_name       VARCHAR(255),
  effective_from   DATE         NOT NULL,
  effective_to     DATE,                   -- NULL = currently active
  PRIMARY KEY (entity_type, internal_code, effective_from)
);
```

### Generating a COSIF balance sheet

```sql
-- Read current balances from the ledger
SELECT
    coa.code            AS internal_code,
    coa.name            AS internal_name,
    coa.account_type,
    coa.current_balance,
    coa.currency,
    e.external_id       AS entity_external_id
FROM chart_of_accounts coa
JOIN entities e ON e.id = coa.entity_id
WHERE e.id = :entity_id
  AND coa.is_active = true;

-- Join with the upstream COSIF mapping table to produce the report
SELECT
    m.cosif_code,
    m.cosif_name,
    SUM(coa.current_balance) AS balance  -- aggregate if multiple internal accounts → one COSIF code
FROM chart_of_accounts coa
JOIN cosif_account_mappings m
  ON m.internal_code = coa.code
  AND m.entity_type  = :entity_type
  AND m.effective_from <= CURRENT_DATE
  AND (m.effective_to IS NULL OR m.effective_to >= CURRENT_DATE)
WHERE coa.entity_id = :entity_id
GROUP BY m.cosif_code, m.cosif_name
ORDER BY m.cosif_code;
```

### Important notes

- COSIF codes depend on the **entity type** (IP vs. SCD vs. bank). The mapping must be parameterized by entity type.
- Multiple internal accounts can map to the same COSIF code — aggregate them.
- COSIF is updated periodically by the BACEN. Use `effective_from`/`effective_to` to version the mapping and never change historical balances.
- Always validate codes against the official COSIF publication before submitting to the BACEN.

---

## 2. Trial Balance

### What it is

A trial balance lists all accounts with their debit and credit totals for a period, confirming that Σ debits = Σ credits. It is the starting point for P&L statements and balance sheets.

### Reading from the ledger

The ledger maintains `current_balance` incrementally. For a point-in-time trial balance, use `account_balance_snapshots`:

```sql
-- Trial balance at end of a specific month (e.g. 2025-12-31)
SELECT
    coa.code,
    coa.name,
    coa.account_type,
    coa.currency,
    snap.balance
FROM account_balance_snapshots snap
JOIN chart_of_accounts coa ON coa.id = snap.account_id
WHERE snap.snapshot_date = '2025-12-31'
  AND coa.entity_id      = :entity_id
ORDER BY coa.code;
```

For a live (current) trial balance:

```sql
SELECT
    code,
    name,
    account_type,
    currency,
    current_balance AS balance
FROM chart_of_accounts
WHERE entity_id = :entity_id
  AND is_active  = true
ORDER BY code;
```

### Validating double-entry

```python
from decimal import Decimal
from collections import defaultdict

def validate_trial_balance(rows):
    totals = defaultdict(Decimal)
    for row in rows:
        if row.account_type in ('asset', 'expense'):
            totals[row.currency] += row.balance   # normal debit balance
        else:
            totals[row.currency] -= row.balance   # normal credit balance
    for currency, net in totals.items():
        if net != 0:
            raise ValueError(f"Trial balance out of balance in {currency}: {net}")
```

---

## 3. Accrual Engine

### What it is

Under accrual accounting (required by BACEN for regulated institutions), revenue and expense are recognized when earned or incurred — not when cash moves. For a 12-month credit operation, one day's worth of interest must be recognized every calendar day.

The ledger supports accrual natively via `effective_date` (the accrual date, not the posting date) and idempotency. The accrual engine lives upstream.

### Engine flow

```
1. Read active credit instruments from the product service
2. For each instrument, compute today's accrual amount:
     daily_interest = outstanding_balance × annual_rate / day_count_convention
3. Post one event per instrument to the ledger with effective_date = accrual_date
4. The ledger records the entries; the engine does not store results
```

### Posting an accrual event

```python
def post_daily_accrual(instrument_id, entity_id, accrual_date, amount, currency):
    return {
        "event_type": "accrual.daily",
        "event_id": f"accrual:{instrument_id}:{accrual_date}",  # idempotency
        "data": {
            "entity_id": entity_id,
            "effective_date": str(accrual_date),
            "transaction_type": "accrual",
            "idempotency_key": f"accrual:{instrument_id}:{accrual_date}",
            "entries": [
                {
                    "account_code": "1.3.001",  # Accrued Interest Receivable
                    "entry_type": "debit",
                    "amount": amount,
                    "currency": currency,
                    "metadata": {
                        "instrument_id": instrument_id,
                        "accrual_date": str(accrual_date),
                        "method": "252_business_days"
                    }
                },
                {
                    "account_code": "3.2.001",  # Revenue - Interest Income
                    "entry_type": "credit",
                    "amount": amount,
                    "currency": currency
                }
            ]
        }
    }
```

### Day-count conventions

| Convention | Used for | Formula |
|---|---|---|
| `252_business_days` | Brazilian financial market standard | `rate_annual / 252` |
| `365_calendar_days` | Consumer credit (CDC) | `rate_annual / 365` |
| `360_calendar_days` | Trade finance | `rate_annual / 360` |
| `30_360` | Some structured products | `rate_annual / (12 × 30)` |

The convention is stored in `metadata` at posting time and never recomputed.

---

## 4. PDD — Allowance for Doubtful Accounts

### What it is

**Resolução CMN nº 2.682** requires financial institutions to classify every credit operation by risk level (AA through H) and maintain mandatory loss provisions. Classification is based on days past due and qualitative risk factors.

### Provisioning rates by risk level

| Rating | Days overdue (reference) | Minimum provision |
|--------|--------------------------|-------------------|
| AA     | 0 (current, low risk)    | 0%                |
| A      | ≤ 14                     | 0.5%              |
| B      | 15 – 30                  | 1%                |
| C      | 31 – 60                  | 3%                |
| D      | 61 – 90                  | 10%               |
| E      | 91 – 120                 | 30%               |
| F      | 121 – 150                | 50%               |
| G      | 151 – 180                | 70%               |
| H      | > 180                    | 100%              |

### Reading the credit portfolio from the ledger

```sql
-- Outstanding credit portfolio per entity
SELECT
    coa.id          AS account_id,
    coa.code,
    coa.current_balance AS outstanding,
    coa.currency
FROM chart_of_accounts coa
WHERE coa.entity_id   = :entity_id
  AND coa.code LIKE '1.6.%'   -- credit operations range
  AND coa.code NOT LIKE '1.6.002%'  -- exclude PDD contra-asset
  AND coa.is_active = true;
```

### Computing required provision

```python
def compute_pdd(outstanding: Decimal, rating: str) -> Decimal:
    rates = {
        'AA': Decimal('0.000'), 'A': Decimal('0.005'), 'B': Decimal('0.01'),
        'C':  Decimal('0.03'),  'D': Decimal('0.10'),  'E': Decimal('0.30'),
        'F':  Decimal('0.50'),  'G': Decimal('0.70'),  'H': Decimal('1.00'),
    }
    return (outstanding * rates[rating]).quantize(Decimal('0.01'))

def compute_provision_delta(current_provision: Decimal, required: Decimal) -> Decimal:
    # Positive = need to constitute more; negative = can reverse
    return required - current_provision
```

### Reading current provision balance from the ledger

```sql
-- Current PDD provision balance (contra-asset, credit balance)
SELECT ABS(current_balance) AS current_provision
FROM chart_of_accounts
WHERE entity_id = :entity_id
  AND code      = '1.6.002';  -- PDD - Allowance
```

### Posting constitution or reversal

```python
def post_pdd_adjustment(entity_id, delta, instrument_id, rating, currency):
    if delta > 0:
        # Constitute additional provision
        entries = [
            {"account_code": "4.3.001", "entry_type": "debit",  "amount": delta},
            {"account_code": "1.6.002", "entry_type": "credit", "amount": delta},
        ]
        tx_type = "pdd_provision"
    else:
        # Reverse excess provision
        entries = [
            {"account_code": "1.6.002", "entry_type": "debit",  "amount": abs(delta)},
            {"account_code": "4.3.001", "entry_type": "credit", "amount": abs(delta)},
        ]
        tx_type = "pdd_reversal"

    return {
        "event_type": f"pdd.{tx_type}",
        "event_id": f"pdd:{instrument_id}:{effective_date}",
        "data": {
            "entity_id": entity_id,
            "effective_date": str(effective_date),
            "transaction_type": tx_type,
            "idempotency_key": f"pdd:{instrument_id}:{effective_date}",
            "entries": [
                {**e, "currency": currency,
                 "metadata": {"instrument_id": instrument_id, "rating": rating,
                              "resolution": "CMN_2682"}}
                for e in entries
            ]
        }
    }
```

---

## 5. Tax Accounting

### 5.1 IOF (Tax on Financial Operations)

IOF is calculated per operation and must be posted **atomically** with the triggering transaction. The event handler calls the tax engine before submitting entries to the ledger; the IOF entry is included in the same event.

**IOF rates (reference — validate against current legislation):**

| Operation | Daily rate | Max period |
|---|---|---|
| Credit (PF) | 0.0082% per day | 365 days |
| Credit (PJ) | 0.0041% per day | 365 days |
| Additional flat | 0.38%  | per operation |
| Foreign exchange | 0.38%  | per operation |

**Computing IOF for a credit operation:**

```python
from decimal import Decimal

def compute_iof_credit(principal: Decimal, days: int, is_pf: bool) -> Decimal:
    daily_rate = Decimal('0.000082') if is_pf else Decimal('0.000041')
    flat_rate  = Decimal('0.0038')
    days_capped = min(days, 365)
    iof = principal * (daily_rate * days_capped + flat_rate)
    return iof.quantize(Decimal('0.01'))
```

**IOF entries (posted as part of the originating transaction):**

```python
iof_entries = [
    {"account_code": "4.2.001", "entry_type": "debit",  "amount": iof_amount,
     "metadata": {"tax_type": "IOF", "rate_daily": "0.000082", "days": days}},
    {"account_code": "2.2.001", "entry_type": "credit", "amount": iof_amount,
     "metadata": {"triggers_transaction_id": originating_tx_id}},
]
```

### 5.2 PIS/COFINS

PIS/COFINS is computed monthly on financial revenue. For institutions in the **cumulative regime** (most financial intermediaries):

| Contribution | Rate   |
|---|---|
| PIS          | 0.65%  |
| COFINS       | 4.00%  |

```python
def compute_pis_cofins(monthly_revenue: Decimal) -> tuple[Decimal, Decimal]:
    pis    = (monthly_revenue * Decimal('0.0065')).quantize(Decimal('0.01'))
    cofins = (monthly_revenue * Decimal('0.04')).quantize(Decimal('0.01'))
    return pis, cofins
```

**Reading monthly revenue from the ledger:**

```sql
-- Sum of all revenue entries for the month
SELECT ABS(SUM(te.amount)) AS total_revenue
FROM transaction_entries te
JOIN chart_of_accounts coa ON coa.id = te.account_id
JOIN transactions t         ON t.id  = te.transaction_id
WHERE coa.entity_id    = :entity_id
  AND coa.account_type = 'revenue'
  AND te.entry_type    = 'credit'
  AND t.effective_date BETWEEN :month_start AND :month_end
  AND t.status         = 'committed';
```

**Posting PIS/COFINS provision (month-end job):**

```python
entries = [
    {"account_code": "4.2.002", "entry_type": "debit",  "amount": pis + cofins},
    {"account_code": "2.2.002", "entry_type": "credit", "amount": pis + cofins,
     "metadata": {"pis": str(pis), "cofins": str(cofins), "base": str(monthly_revenue)}},
]
event = {
    "transaction_type": "tax_provision",
    "idempotency_key": f"pis_cofins:{entity_id}:{year_month}",
    "effective_date": str(month_end_date),
}
```

### 5.3 CSLL / IRPJ

CSLL (15% for financial institutions) and IRPJ (15% + 10% surtax on profit above R$20k/month) are computed on net profit. Read the P&L from the ledger, compute the tax, and post a monthly estimate.

```python
def compute_csll_irpj(net_profit: Decimal) -> tuple[Decimal, Decimal]:
    csll = (net_profit * Decimal('0.15')).quantize(Decimal('0.01'))

    irpj_base = net_profit * Decimal('0.15')
    surtax_base = max(net_profit - Decimal('20000'), Decimal('0'))
    irpj = (irpj_base + surtax_base * Decimal('0.10')).quantize(Decimal('0.01'))

    return csll, irpj
```

**Reading net profit from the ledger:**

```sql
-- Net result for the period: revenues - expenses
SELECT
    SUM(CASE WHEN coa.account_type = 'revenue' THEN ABS(coa.current_balance) ELSE 0 END)
  - SUM(CASE WHEN coa.account_type = 'expense' THEN coa.current_balance        ELSE 0 END)
    AS net_profit
FROM chart_of_accounts coa
WHERE coa.entity_id = :entity_id;
```

---

## 6. Period Closing

### Flow

```
1. Upstream layer computes the trial balance for the period
2. Upstream layer generates closing entries (zeroing revenues and expenses)
3. Upstream layer posts closing entries to the ledger as transaction_type: "period_closing"
4. Upstream layer requests the ledger to close the period
5. After regulatory submission, upstream layer requests the ledger to lock the period
```

### Step 1 — Compute net result

```sql
SELECT
    SUM(CASE WHEN account_type = 'revenue' THEN ABS(current_balance) ELSE 0 END) AS total_revenue,
    SUM(CASE WHEN account_type = 'expense' THEN current_balance       ELSE 0 END) AS total_expense,
    SUM(CASE WHEN account_type = 'revenue' THEN ABS(current_balance) ELSE 0 END)
  - SUM(CASE WHEN account_type = 'expense' THEN current_balance       ELSE 0 END) AS net_result
FROM chart_of_accounts
WHERE entity_id = :entity_id;
```

### Step 2 — Generate closing entries

```python
def build_closing_entries(revenue_accounts, expense_accounts, net_result, currency):
    entries = []

    # Zero out all revenue accounts (debit to close credit-balance accounts)
    for acc in revenue_accounts:
        entries.append({"account_code": acc.code, "entry_type": "debit",
                        "amount": abs(acc.current_balance), "currency": currency})

    # Zero out all expense accounts (credit to close debit-balance accounts)
    for acc in expense_accounts:
        entries.append({"account_code": acc.code, "entry_type": "credit",
                        "amount": acc.current_balance, "currency": currency})

    # Transfer net result to Net Income / Retained Earnings
    entry_type = "credit" if net_result >= 0 else "debit"
    entries.append({"account_code": "2.4.001", "entry_type": entry_type,
                    "amount": abs(net_result), "currency": currency,
                    "metadata": {"closing_period": period_label}})
    return entries
```

### Step 3 — Post closing transaction

```python
event = {
    "event_type": "period.closing",
    "event_id":   f"period_closing:{entity_id}:{period_label}",
    "data": {
        "entity_id":        entity_id,
        "effective_date":   str(period_last_day),   # e.g. "2025-12-31"
        "transaction_type": "period_closing",
        "idempotency_key":  f"period_closing:{entity_id}:{period_label}",
        "description":      f"Period closing — {period_label}",
        "entries":          closing_entries,
    }
}
```

### Step 4 — Request period close via ledger API

```http
POST /periods/{period_date}/close
{
  "closed_by": "fiscal-service-v1",
  "notes": "Month-end close 2025-12"
}
```

After the BACEN submission is confirmed:

```http
POST /periods/{period_date}/lock
{
  "locked_by": "compliance-service",
  "notes": "BACEN submission confirmed — DLO ref #98765"
}
```

Once locked, any attempt to post an entry with `effective_date` in that period will be rejected by the ledger with a `PeriodLockedError`.

---

## 7. Adapting to Other Regulatory Frameworks

Because all regulatory logic lives in the upstream layer, porting open-ledger to a different jurisdiction means implementing a new upstream layer — not changing the ledger. The sections below map each Brazilian requirement to its closest international equivalent.

### European Union

The EU regulatory framework is built on **IFRS** internalized via European law, with the **European Banking Authority (EBA)** defining reporting templates.

| Brazilian requirement | EU equivalent | Notes |
|---|---|---|
| COSIF account mapping | **FINREP** (EBA Financial Reporting) | FINREP defines reporting templates, not internal CoA structure. Map internal codes to FINREP taxonomy at report time. |
| PDD (Res. CMN 2.682) | **ECL — IFRS 9** (Expected Credit Loss) | IFRS 9 uses a 3-stage model (Stage 1: 12-month ECL; Stage 2/3: lifetime ECL) instead of AA→H buckets. The ledger entries are identical — only the upstream calculation changes. |
| IOF | **No direct equivalent** | Some EU member states apply stamp duty or financial transaction taxes on specific operations. Apply as needed per country. |
| PIS/COFINS | **VAT** on financial services | EU VAT treatment of financial services is complex (largely exempt but with partial recovery rules). Consult local tax counsel. |
| CSLL / IRPJ | **Corporate income tax** | Each member state sets its own rate. The provisioning pattern (debit Expense / credit Tax Payable) is identical. |
| BACEN regulatory submission | **COREP / FINREP** submissions to national regulator | Same upstream pattern: compute from ledger data, submit via EBA XBRL taxonomy. |

### United States

The US framework is built on **US GAAP (FASB)** with regulatory reporting defined by the **FFIEC** for bank holding companies.

| Brazilian requirement | US equivalent | Notes |
|---|---|---|
| COSIF account mapping | **Call Reports** (FFIEC 031/041/051) | Call Reports define what categories to report, not the internal CoA. Map internal accounts to Call Report schedules (RC, RI, etc.) at report time. |
| PDD (Res. CMN 2.682) | **CECL — ASC 326** (Current Expected Credit Loss) | CECL replaced the incurred-loss model in 2020. Uses lifetime expected losses from day one. Same ledger entries (debit Expense / credit Allowance), different upstream calculation. |
| IOF | **No federal equivalent** | Some states impose financial transaction taxes. |
| PIS/COFINS | **No direct equivalent** | Federal excise tax applies to some financial products. State sales taxes vary. |
| CSLL / IRPJ | **Federal income tax** (21% federal rate + state) | Same provisioning pattern. |

### United Kingdom

Post-Brexit, the UK operates under **UK GAAP / UK-adopted IFRS** with **PRA** (Prudential Regulation Authority) and **FCA** reporting requirements.

| Brazilian requirement | UK equivalent | Notes |
|---|---|---|
| COSIF | **PRA regulatory returns** (COREP, FINREP adapted) | Similar to EU FINREP. Map at report time. |
| PDD | **ECL — IFRS 9** (UK-adopted) | Identical to EU treatment. |
| IOF | **Stamp Duty Reserve Tax (SDRT)** on some instruments | Apply per operation where applicable. |
| PIS/COFINS | **VAT** (largely exempt for financial services) | |
| CSLL / IRPJ | **Corporation Tax** (25% from 2023) | Same provisioning pattern. |

### General pattern for any jurisdiction

Regardless of the country, the implementation pattern is always:

```
1. Identify the regulatory reporting framework (who is the regulator, what do they require)
2. Build a mapping table: internal account codes → regulatory codes
3. Implement the credit loss model (IFRS 9 ECL, CECL, or local equivalent)
4. Implement the tax engine for local indirect and direct taxes
5. Connect to the ledger via the same event interface (debit/credit pairs)
6. The ledger schema does not change
```

The only ledger-side change that may be needed is provisioning the right accounts in the `chart_of_accounts` templates — account names and codes are free-form and can follow any convention. Everything else is upstream.

---

## Reference — transaction_type Conventions

| `transaction_type`   | Posted by         | Description                              |
|----------------------|-------------------|------------------------------------------|
| `sale`               | Product service   | Card sale, payment received              |
| `anticipation`       | Product service   | Early payment of a receivable            |
| `settlement`         | Settlement service| Cash transferred out / receivable closed |
| `reversal`           | Any service       | Mirror entries offsetting a prior tx     |
| `accrual`            | Accrual engine    | Daily interest recognition               |
| `tax_provision`      | Tax engine        | IOF, PIS/COFINS, CSLL/IRPJ provision     |
| `pdd_provision`      | Credit risk engine| PDD constitution (Res. CMN 2.682)        |
| `pdd_reversal`       | Credit risk engine| PDD reversal (upgrade or payoff)         |
| `period_closing`     | Fiscal service    | Revenue/expense zeroing at month-end     |
| `suspense_capture`   | Settlement service| Unallocated funds received               |
| `suspense_release`   | Reconciliation    | Suspense funds allocated to destination  |
