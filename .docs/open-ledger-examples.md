# Open Ledger — Business Scenario Examples

This document extends the core spec with scenarios not covered by the four basic examples. Each scenario shows the inbound event, the entries posted, and the resulting account state. Use these as implementation and test references.

The merchant template from the spec is used throughout unless noted otherwise.

---

## Scenario 1 — Installment Sale (3× interest-free)

**Context:** A $300.00 sale split into 3 equal installments of $100.00 each. MDR 2%, platform fee 0.3%. One ledger transaction is created; three receivable rows track each installment's settlement date independently.

**Inbound event:**
```json
{
  "event_type": "transaction.created",
  "event_id": "evt_010",
  "data": {
    "transaction_id": "txn_300",
    "entity_id": "abc-123",
    "gross_amount": 300.00,
    "installments": 3,
    "mdr_rate": 0.02,
    "platform_fee_rate": 0.003,
    "settlement_dates": ["2026-01-30", "2026-02-28", "2026-03-30"]
  }
}
```

**Entries posted (6 balanced legs — same structure as a single-payment sale, for the total):**

| # | Account                    | Type   | Amount   | Key metadata                        |
|---|----------------------------|--------|----------|-------------------------------------|
| 1 | 1.1.001 Receivables        | debit  | $300.00  | transaction_id: txn_300             |
| 2 | 3.1.001 Revenue - Sales    | credit | $300.00  | installments: 3                     |
| 3 | 4.1.001 Expense - MDR      | debit  |   $6.00  | mdr_rate: 0.02, formula: "300×0.02" |
| 4 | 1.1.001 Receivables        | credit |   $6.00  | —                                   |
| 5 | 4.1.002 Expense - Platform | debit  |   $0.90  | platform_fee_rate: 0.003            |
| 6 | 1.1.001 Receivables        | credit |   $0.90  | —                                   |

> **Balance check:** $306.90 total debits = $306.90 total credits ✓  
> **Net receivables:** $293.10 — split into 3 receivable rows of $97.70 each.

**Receivables table (3 rows created, one per installment):**

| receivable | gross_amount | net_amount | expected_settlement_date |
|------------|-------------|------------|--------------------------|
| recv_01    | $100.00      | $97.70     | 2026-01-30               |
| recv_02    | $100.00      | $97.70     | 2026-02-28               |
| recv_03    | $100.00      | $97.70     | 2026-03-30               |

> **Design note:** Entries are posted at the total amount — the ledger records the full financial obligation in one atomic operation. The `receivables` table is the installment tracker. Each installment settles independently: future `settlement.completed` events debit World and credit Receivables for each installment's `net_amount`.

---

## Scenario 2 — Marketplace Split Payment

**Context:** A $100.00 sale is split between a merchant and the platform. MDR 2% ($2.00), platform fee 10% ($10.00) charged to the merchant. One inbound event triggers two independent ledger transactions — one per entity. Entity accounts are fully isolated.

**Inbound event:**
```json
{
  "event_type": "transaction.created",
  "event_id": "evt_020",
  "data": {
    "transaction_id": "txn_split",
    "gross_amount": 100.00,
    "mdr_rate": 0.02,
    "splits": [
      { "entity_id": "merchant-001", "role": "seller",   "platform_fee_rate": 0.10 },
      { "entity_id": "platform-001", "role": "platform", "platform_fee_rate": 0.00 }
    ]
  }
}
```

**Transaction A — merchant-001:**

| # | Account                    | Type   | Amount  | Key metadata              |
|---|----------------------------|--------|---------|---------------------------|
| 1 | 1.1.001 Receivables        | debit  | $100.00 | transaction_id: txn_split |
| 2 | 3.1.001 Revenue - Sales    | credit | $100.00 | —                         |
| 3 | 4.1.001 Expense - MDR      | debit  |   $2.00 | mdr_rate: 0.02            |
| 4 | 1.1.001 Receivables        | credit |   $2.00 | —                         |
| 5 | 4.1.002 Expense - Platform | debit  |  $10.00 | platform_fee_rate: 0.10   |
| 6 | 1.1.001 Receivables        | credit |  $10.00 | —                         |

> **Merchant net receivables: $88.00**

**Transaction B — platform-001:**

| # | Account                         | Type   | Amount  | Key metadata                    |
|---|---------------------------------|--------|---------|---------------------------------|
| 1 | 1.1.001 Receivables             | debit  | $10.00  | transaction_id: txn_split       |
| 2 | 3.1.001 Revenue - Platform Fee  | credit | $10.00  | source_entity: merchant-001     |

> **Platform receivables: $10.00**

**Idempotency keys:**
- Merchant: `"sale:txn_split:merchant-001"`
- Platform: `"sale:txn_split:platform-001"`

> **Design note:** Each entity's books are fully isolated — they share only the `reference_id`. Linking is done via `reference_type = "transaction"` and `reference_id = "txn_split"` on both ledger transactions. If the platform also bears MDR on its portion, add the expense legs to Transaction B.

---

## Scenario 3 — Chargeback Post-Settlement

**Context:** The sale from Spec Example 1 ($97.70 net) was settled directly (no anticipation). A chargeback now arrives. Requires two events: one to bring the money back into the system via the World account, and one to reverse the original sale.

**State before chargeback:**

| Account                    | Balance  |
|----------------------------|----------|
| 1.1.001 Receivables        | $0       |
| 3.1.001 Revenue - Sales    | +$100.00 |
| 4.1.001 Expense - MDR      | +$2.00   |
| 4.1.002 Expense - Platform | +$0.30   |
| 9.9.999 World              | +$97.70 debit (money left the system at settlement) |

**Event 1 — `chargeback.received` (money returns from merchant's bank):**

```json
{
  "event_type": "chargeback.received",
  "event_id": "evt_030",
  "data": {
    "chargeback_id": "cb_001",
    "entity_id": "abc-123",
    "transaction_id": "txn_123",
    "amount": 97.70,
    "bank_reference": "CHBK_99999"
  }
}
```

| # | Account             | Type   | Amount  | Key metadata               |
|---|---------------------|--------|---------|----------------------------|
| 1 | 1.1.001 Receivables | debit  | $97.70  | chargeback_id: cb_001      |
| 2 | 9.9.999 World       | credit | $97.70  | bank_reference: CHBK_99999 |

After event 1: Receivables = $97.70, World = $0.

**Event 2 — `transaction.reversed` (mirror of the original sale):**

```json
{
  "event_type": "transaction.reversed",
  "event_id": "evt_031",
  "data": {
    "reversal_id": "rev_001",
    "transaction_id": "txn_123",
    "entity_id": "abc-123",
    "reason": "chargeback",
    "amount": 100.00
  }
}
```

| # | Account                    | Type   | Amount  | Key metadata                             |
|---|----------------------------|--------|---------|------------------------------------------|
| 1 | 3.1.001 Revenue - Sales    | debit  | $100.00 | reversal_id: rev_001, reason: chargeback |
| 2 | 1.1.001 Receivables        | credit | $100.00 | —                                        |
| 3 | 1.1.001 Receivables        | debit  |   $2.00 | reversal: mdr_fee                        |
| 4 | 4.1.001 Expense - MDR      | credit |   $2.00 | —                                        |
| 5 | 1.1.001 Receivables        | debit  |   $0.30 | reversal: platform_fee                   |
| 6 | 4.1.002 Expense - Platform | credit |   $0.30 | —                                        |

**Final state — all accounts at $0:**

| Account                    | Calculation                         | Balance |
|----------------------------|-------------------------------------|---------|
| 1.1.001 Receivables        | $97.70 − $100.00 + $2.00 + $0.30   | **$0**  |
| 3.1.001 Revenue - Sales    | $100.00 − $100.00                   | **$0**  |
| 4.1.001 Expense - MDR      | $2.00 − $2.00                       | **$0**  |
| 4.1.002 Expense - Platform | $0.30 − $0.30                       | **$0**  |
| 9.9.999 World              | $97.70 − $97.70                     | **$0**  |

> **Balance check:** ✓ Full round-trip — every dollar that entered the system has left.

> **Design note:** The chargeback amount in Event 1 is the *settled* amount ($97.70), not the gross ($100.00). The $2.30 gap is recovered by reversing the fee entries in Event 2. If the acquirer charges a chargeback fee (e.g. $15.00), add a debit to an `Expense - Chargeback Fee` account in Event 1 to record that additional cost — it stays as a real expense and does not zero out.

---

## Scenario 4 — Partial Anticipation

**Context:** Merchant has $97.70 in Receivables across two installments ($47.70 due 2026-01-30 and $50.00 due 2026-02-28). They anticipate only the $50.00 installment. Rate: 1.5%, fee = $0.75 (HALF_UP: $50.00 × 0.015 = $0.75 exactly).

**Inbound event:**
```json
{
  "event_type": "anticipation.created",
  "event_id": "evt_040",
  "data": {
    "anticipation_id": "ant_partial",
    "entity_id": "abc-123",
    "receivable_ids": ["recv_02"],
    "receivable_amount": 50.00,
    "anticipation_rate": 0.015,
    "anticipation_fee": 0.75,
    "net_amount": 49.25,
    "days_advanced": 20,
    "original_settlement_date": "2026-02-28"
  }
}
```

**Entries posted:**

| # | Account                            | Type   | Amount  | Key metadata                     |
|---|------------------------------------|--------|---------|----------------------------------|
| 1 | 1.1.002 Receivables Anticipated    | debit  | $50.00  | anticipation_id: ant_partial     |
| 2 | 1.1.001 Receivables                | credit | $50.00  | receivable_id: recv_02           |
| 3 | 4.1.003 Expense - Anticipation Fee | debit  |  $0.75  | rate: 0.015, days_advanced: 20   |
| 4 | 1.1.002 Receivables Anticipated    | credit |  $0.75  | formula: "50.00 × 0.015"         |

> **Balance check:** $50.75 total debits = $50.75 total credits ✓

**State after:**

| Account                         | Balance |
|---------------------------------|---------|
| 1.1.001 Receivables             | $47.70  |
| 1.1.002 Receivables Anticipated | $49.25  |

> **Design note:** Only `recv_02` is reclassified. `recv_01` ($47.70) stays in 1.1.001 Receivables and follows the normal settlement path on 2026-01-30. The two receivables now have independent lifecycles — one anticipated, one not.

---

## Scenario 5 — Anticipation Cancellation

**Context:** Merchant requested anticipation `ant_456` ($96.23 net, from Spec Example 2) but the processor rejects it before disbursement. The anticipation is cancelled; the receivable reverts to its original state and the fee is fully refunded.

This reverses Spec Example 2 entirely.

**Inbound event:**
```json
{
  "event_type": "anticipation.cancelled",
  "event_id": "evt_050",
  "data": {
    "anticipation_id": "ant_456",
    "entity_id": "abc-123",
    "receivable_amount": 97.70,
    "anticipation_fee": 1.47,
    "reason": "credit_denied"
  }
}
```

**Entries posted (mirror of Spec Example 2):**

| # | Account                            | Type   | Amount  | Key metadata                          |
|---|------------------------------------|--------|---------|---------------------------------------|
| 1 | 1.1.001 Receivables                | debit  | $97.70  | anticipation_id: ant_456, reason: credit_denied |
| 2 | 1.1.002 Receivables Anticipated    | credit | $97.70  | —                                     |
| 3 | 1.1.002 Receivables Anticipated    | debit  |  $1.47  | reversal: anticipation_fee            |
| 4 | 4.1.003 Expense - Anticipation Fee | credit |  $1.47  | —                                     |

> **Balance check:** $99.17 total debits = $99.17 total credits ✓

**State after:**

| Account                            | Balance |
|------------------------------------|---------|
| 1.1.001 Receivables                | $97.70 (restored) |
| 1.1.002 Receivables Anticipated    | $0      |
| 4.1.003 Expense - Anticipation Fee | $0 (fee refunded) |

> **Design note:** The fee is refunded because the anticipation never resulted in a disbursement. If cancellation happens *after* disbursement (the merchant received funds and is returning them), the flow resembles Scenario 3 — the fee may or may not be refundable depending on business rules, and if kept, it remains as a real expense that does not zero out.

---

## Scenario 6 — Batch Settlement

**Context:** Three receivables for the same entity ($97.70, $85.00, $200.00) are settled in a single bank wire of $382.70. One ledger transaction captures the entire batch; each leg references its receivable in metadata.

**Inbound event:**
```json
{
  "event_type": "settlement.completed",
  "event_id": "evt_060",
  "data": {
    "settlement_id": "settle_batch_01",
    "entity_id": "abc-123",
    "total_amount": 382.70,
    "bank_reference": "WIRE_BATCH_001",
    "settlement_date": "2026-01-30",
    "receivables": [
      { "receivable_id": "recv_01", "amount": 97.70 },
      { "receivable_id": "recv_04", "amount": 85.00 },
      { "receivable_id": "recv_05", "amount": 200.00 }
    ]
  }
}
```

**Entries posted (2 legs per receivable, all within one transaction):**

| # | Account                 | Type   | Amount   | Key metadata             |
|---|-------------------------|--------|----------|--------------------------|
| 1 | 9.9.999 World           | debit  |  $97.70  | receivable_id: recv_01   |
| 2 | 1.1.001 Receivables     | credit |  $97.70  | —                        |
| 3 | 9.9.999 World           | debit  |  $85.00  | receivable_id: recv_04   |
| 4 | 1.1.001 Receivables     | credit |  $85.00  | —                        |
| 5 | 9.9.999 World           | debit  | $200.00  | receivable_id: recv_05   |
| 6 | 1.1.001 Receivables     | credit | $200.00  | —                        |

> **Balance check:** $382.70 total debits = $382.70 total credits ✓

> **Design note:** One entry per receivable (rather than a single aggregated pair) preserves full traceability — each leg links to a specific receivable in its metadata. One `event_log` row, one `transaction` header, six `transaction_entries`. World accumulates a $382.70 debit balance representing the single bank wire.

---

## Scenario 7 — Idempotency in Action

**Context:** A message broker delivers the same `settlement.completed` event twice (at-least-once delivery). The first delivery succeeds; the second must be silently rejected without double-posting entries or double-updating balances.

**First delivery — processed normally:**
1. `event_log` row inserted: `status = received`
2. Entries posted, balances updated
3. `event_log` row updated: `status = processed`

**Second delivery — same `event_id` + `event_type`:**
1. INSERT into `event_log` fails: `UNIQUE (event_id, event_type)` violated
2. Handler catches the constraint violation and returns immediately
3. No transaction, no entries, no balance change

**Upstream retry with a new broker message ID (same business operation, new `event_id`):**
1. `event_log` INSERT succeeds (new `event_id`)
2. Handler builds the transaction and attempts INSERT into `transactions`
3. INSERT fails: `UNIQUE (idempotency_key)` violated (`"settlement:settle_789"` already exists)
4. Handler catches the violation, updates `event_log` row to `status = skipped`
5. No entries, no balance change

```
Layer 1 — event_log(event_id, event_type) UNIQUE
  └─ guards against broker redelivery of the exact same message

Layer 2 — transactions(idempotency_key) UNIQUE
  └─ guards against upstream retrying with a new message ID for the same business operation
```

> **Design note:** Both layers are necessary. Layer 1 alone fails if the upstream broker generates a fresh message ID on retry. Layer 2 alone fails if the event_log check is bypassed or the handler crashes after inserting the event but before creating the transaction. The `skipped` status distinguishes "deduplicated" from "failed" in the audit log.

---

## Scenario 8 — Pending → Committed Lifecycle

**Context:** A pre-authorization creates a `pending` transaction. Entries are recorded immediately, but `current_balance` is not updated — the amount is invisible to balance reads until the authorization is captured. If capture never happens, the transaction is voided with no balance impact.

**Event 1 — `authorization.created` (pending transaction):**
```json
{
  "event_type": "authorization.created",
  "event_id": "evt_080",
  "data": {
    "authorization_id": "auth_001",
    "entity_id": "abc-123",
    "gross_amount": 150.00,
    "mdr_rate": 0.02,
    "platform_fee_rate": 0.003
  }
}
```

Handler inserts `transaction` with `status = pending` and posts all entries into `transaction_entries`. **The `SELECT FOR UPDATE` balance update loop is skipped entirely.** `current_balance` is unchanged.

**State after Event 1:**

| | |
|---|---|
| `transactions.status` | `pending` |
| 1.1.001 Receivables `current_balance` | unchanged (e.g. $0) |
| Entries in `transaction_entries` | exist, 6 rows |

**Path A — `authorization.captured` (commits, balance is updated):**
```json
{
  "event_type": "authorization.captured",
  "event_id": "evt_081",
  "data": { "authorization_id": "auth_001", "entity_id": "abc-123" }
}
```

Handler:
1. Looks up the existing `pending` transaction by `idempotency_key = "authorization:auth_001"`
2. Runs the `SELECT FOR UPDATE` balance update loop over all entries already in `transaction_entries`
3. Sets `transactions.status = committed`

All balance updates happen in the same DB transaction as the status change.

**Path B — `authorization.voided` (cancelled before capture):**
```json
{
  "event_type": "authorization.voided",
  "event_id": "evt_082",
  "data": { "authorization_id": "auth_001", "entity_id": "abc-123" }
}
```

Handler sets `transactions.status = voided`. No new entries. No balance change. Entries already in `transaction_entries` remain as an audit record but are permanently ignored by the balance layer.

```
pending ──captured──▶ committed ──(new reversal txn)──▶ balances corrected
   └────voided────▶ voided       (no balance impact; entries kept for audit)
```

> **Design note:** Voiding is only valid from `pending`. A `committed` transaction cannot be voided — post a new transaction with reversing entries instead (see Spec Example 4). This distinction is enforced at the handler level, not by a DB constraint.

---

## Scenario 9 — Multi-level Payfac: Fee Cascade (3 levels)

**Context:** Fintech A owns the platform. Company B is a white-label operator (child of Fintech A). Merchant B1 sells through Company B's platform (child of Company B). One sale triggers three ledger transactions — one per entity in the hierarchy.

**Entity tree:**
```
fintech-a   (parent = NULL)          ← root platform
└── company-b   (parent = fintech-a) ← white-label operator
    └── merchant-b1 (parent = company-b) ← end seller
```

**Fee agreement:**
- MDR 2% — borne by Merchant B1, paid to external acquirer (not a ledger entity)
- Platform fee 1% — Company B charges Merchant B1
- White-label fee 0.5% of gross — Fintech A charges Company B

**Inbound event:**
```json
{
  "event_type": "transaction.created",
  "event_id": "evt_090",
  "data": {
    "transaction_id": "txn_b1_001",
    "entity_id": "merchant-b1",
    "gross_amount": 100.00,
    "mdr_rate": 0.02,
    "platform_fee_rate": 0.01,
    "expected_settlement_date": "2026-02-28"
  }
}
```

Handler resolves the entity tree: `merchant-b1 → company-b → fintech-a (NULL, stop)`.  
Three ledger transactions are created atomically.

---

**Transaction 1 — merchant-b1** (`idempotency_key: "sale:txn_b1_001:merchant-b1"`)

| # | Account                    | Type   | Amount   | Key metadata                       |
|---|----------------------------|--------|----------|------------------------------------|
| 1 | 1.1.001 Receivables        | debit  | $100.00  | transaction_id: txn_b1_001         |
| 2 | 3.1.001 Revenue - Sales    | credit | $100.00  | —                                  |
| 3 | 4.1.001 Expense - MDR      | debit  |   $2.00  | mdr_rate: 0.02                     |
| 4 | 1.1.001 Receivables        | credit |   $2.00  | —                                  |
| 5 | 4.1.002 Expense - Platform | debit  |   $1.00  | platform_fee_rate: 0.01, payee: company-b |
| 6 | 1.1.001 Receivables        | credit |   $1.00  | —                                  |

> **Merchant B1 net receivables: $97.00**

---

**Transaction 2 — company-b** (`idempotency_key: "platform_fee:txn_b1_001:company-b"`)

| # | Account                          | Type   | Amount  | Key metadata                          |
|---|----------------------------------|--------|---------|---------------------------------------|
| 1 | 1.1.001 Receivables              | debit  | $1.00   | source_entity: merchant-b1            |
| 2 | 3.1.001 Revenue - Platform Fee   | credit | $1.00   | transaction_id: txn_b1_001            |
| 3 | 4.1.001 Expense - White-label Fee| debit  | $0.50   | whitelabel_rate: 0.005, payee: fintech-a |
| 4 | 1.1.001 Receivables              | credit | $0.50   | formula: "100.00 × 0.005"             |

> **Company B net receivables: $0.50**

---

**Transaction 3 — fintech-a** (`idempotency_key: "whitelabel_fee:txn_b1_001:fintech-a"`)

| # | Account                            | Type   | Amount  | Key metadata                |
|---|------------------------------------|--------|---------|-----------------------------|
| 1 | 1.1.001 Receivables                | debit  | $0.50   | source_entity: company-b    |
| 2 | 3.1.002 Revenue - White-label Fee  | credit | $0.50   | transaction_id: txn_b1_001  |

> **Fintech A receivables from this transaction: $0.50**

---

**Final state across all entities:**

| Entity      | Account                     | Balance  |
|-------------|-----------------------------|----------|
| merchant-b1 | 1.1.001 Receivables         | +$97.00  |
| merchant-b1 | 3.1.001 Revenue - Sales     | +$100.00 |
| merchant-b1 | 4.1.001 Expense - MDR       | +$2.00   |
| merchant-b1 | 4.1.002 Expense - Platform  | +$1.00   |
| company-b   | 1.1.001 Receivables         | +$0.50   |
| company-b   | 3.1.001 Revenue - Plat. Fee | +$1.00   |
| company-b   | 4.1.001 Expense - W-L Fee   | +$0.50   |
| fintech-a   | 1.1.001 Receivables         | +$0.50   |
| fintech-a   | 3.1.002 Revenue - W-L Fee   | +$0.50   |

> **Design note:** The handler is the only place that knows the fee cascade rules. The ledger has no concept of "parent takes a cut" — it just records three independent, balanced transactions linked by the same `reference_id`. Each entity sees only its own accounts. Adding a fourth level (e.g., a regional operator between Fintech A and Company B) requires zero schema changes — the handler just walks one extra step up the tree.

---

## Scenario 10 — Direct Merchant vs. Operated Merchant

**Context:** Two merchants in the same ledger, same sale amount ($100.00), but different positions in the entity tree. Merchant Direct is owned by Fintech A with no operator in between. Merchant B1 is owned by Company B (Scenario 9). The contrast shows how the tree depth determines the fee cascade without any special-casing in the schema.

**Entity tree:**
```
fintech-a
├── merchant-direct (parent = fintech-a) ← no operator
└── company-b       (parent = fintech-a)
    └── merchant-b1 (parent = company-b)
```

**Fee agreements:**
- MDR 2% for both merchants
- Merchant Direct → pays 1.5% platform fee directly to Fintech A
- Merchant B1 → pays 1% platform fee to Company B; Company B pays 0.5% white-label fee to Fintech A

---

**Merchant Direct — 2 transactions (depth 2):**

*Transaction 1 — merchant-direct:*

| # | Account                    | Type   | Amount  |
|---|----------------------------|--------|---------|
| 1 | 1.1.001 Receivables        | debit  | $100.00 |
| 2 | 3.1.001 Revenue - Sales    | credit | $100.00 |
| 3 | 4.1.001 Expense - MDR      | debit  |   $2.00 |
| 4 | 1.1.001 Receivables        | credit |   $2.00 |
| 5 | 4.1.002 Expense - Platform | debit  |   $1.50 |
| 6 | 1.1.001 Receivables        | credit |   $1.50 |

*Transaction 2 — fintech-a (direct platform fee):*

| # | Account                           | Type   | Amount  |
|---|-----------------------------------|--------|---------|
| 1 | 1.1.001 Receivables               | debit  | $1.50   |
| 2 | 3.1.001 Revenue - Platform Fee    | credit | $1.50   |

---

**Merchant B1 — 3 transactions (depth 3):** _(see Scenario 9)_

---

**Side-by-side comparison:**

| | Merchant Direct | Merchant B1 (via Company B) |
|---|---|---|
| Gross sale | $100.00 | $100.00 |
| MDR expense | $2.00 | $2.00 |
| Platform fee expense | $1.50 (to Fintech A) | $1.00 (to Company B) |
| **Merchant net receivables** | **$96.50** | **$97.00** |
| Company B revenue | — | $1.00 → $0.50 net |
| Fintech A revenue | $1.50 | $0.50 |
| Ledger transactions created | 2 | 3 |
| Handler tree traversal | 2 levels | 3 levels |

> **Design note:** The handler loop is identical in both cases — walk `parent_entity_id` until NULL, create a transaction per hop. No conditional logic for "is this a direct merchant?". The fee rates come from the fee agreement stored per entity relationship, not from the entity type.

---

## Scenario 11 — Cascading Chargeback (Multi-level Reversal)

**Context:** The sale from Scenario 9 (Merchant B1, $100.00, not yet settled) receives a chargeback. The reversal must propagate up the entire entity tree — every fee transaction created on the way up must be reversed on the way down.

**State before chargeback (from Scenario 9):**
- merchant-b1: Receivables +$97.00, Revenue +$100.00, Expense-MDR +$2.00, Expense-Platform +$1.00
- company-b: Receivables +$0.50, Revenue-Platform +$1.00, Expense-W-L +$0.50
- fintech-a: Receivables +$0.50, Revenue-W-L +$0.50

**Inbound event:**
```json
{
  "event_type": "transaction.reversed",
  "event_id": "evt_110",
  "data": {
    "reversal_id": "rev_b1_001",
    "transaction_id": "txn_b1_001",
    "entity_id": "merchant-b1",
    "reason": "chargeback",
    "amount": 100.00
  }
}
```

Handler resolves the same entity tree as the original sale and creates one reversal transaction per entity.

---

**Reversal Transaction 1 — merchant-b1** (`idempotency_key: "reversal:rev_b1_001:merchant-b1"`)

Mirror of Transaction 1 from Scenario 9:

| # | Account                    | Type   | Amount  | Key metadata                  |
|---|----------------------------|--------|---------|-------------------------------|
| 1 | 3.1.001 Revenue - Sales    | debit  | $100.00 | reversal_id: rev_b1_001       |
| 2 | 1.1.001 Receivables        | credit | $100.00 | reason: chargeback            |
| 3 | 1.1.001 Receivables        | debit  |   $2.00 | reversal: mdr_fee             |
| 4 | 4.1.001 Expense - MDR      | credit |   $2.00 | —                             |
| 5 | 1.1.001 Receivables        | debit  |   $1.00 | reversal: platform_fee        |
| 6 | 4.1.002 Expense - Platform | credit |   $1.00 | —                             |

---

**Reversal Transaction 2 — company-b** (`idempotency_key: "reversal:rev_b1_001:company-b"`)

Mirror of Transaction 2 from Scenario 9:

| # | Account                           | Type   | Amount  | Key metadata            |
|---|-----------------------------------|--------|---------|-------------------------|
| 1 | 3.1.001 Revenue - Platform Fee    | debit  | $1.00   | reversal_id: rev_b1_001 |
| 2 | 1.1.001 Receivables               | credit | $1.00   | —                       |
| 3 | 1.1.001 Receivables               | debit  | $0.50   | reversal: whitelabel_fee|
| 4 | 4.1.001 Expense - White-label Fee | credit | $0.50   | —                       |

---

**Reversal Transaction 3 — fintech-a** (`idempotency_key: "reversal:rev_b1_001:fintech-a"`)

Mirror of Transaction 3 from Scenario 9:

| # | Account                            | Type   | Amount  | Key metadata            |
|---|------------------------------------|--------|---------|-------------------------|
| 1 | 3.1.002 Revenue - White-label Fee  | debit  | $0.50   | reversal_id: rev_b1_001 |
| 2 | 1.1.001 Receivables                | credit | $0.50   | —                       |

---

**Final state — all accounts at $0 across all entities:**

| Entity      | Account                     | Balance |
|-------------|-----------------------------|---------|
| merchant-b1 | 1.1.001 Receivables         | **$0**  |
| merchant-b1 | 3.1.001 Revenue - Sales     | **$0**  |
| merchant-b1 | 4.1.001 Expense - MDR       | **$0**  |
| merchant-b1 | 4.1.002 Expense - Platform  | **$0**  |
| company-b   | 1.1.001 Receivables         | **$0**  |
| company-b   | 3.1.001 Revenue - Plat. Fee | **$0**  |
| company-b   | 4.1.001 Expense - W-L Fee   | **$0**  |
| fintech-a   | 1.1.001 Receivables         | **$0**  |
| fintech-a   | 3.1.002 Revenue - W-L Fee   | **$0**  |

> **Balance check:** ✓ Every entry posted in Scenario 9 is exactly offset.

> **Design note:** The cascading reversal follows the same tree-walk logic as the original sale — the handler is symmetrical. Each reversal transaction has its own `idempotency_key` scoped to `(reversal_id, entity_id)`, so broker retries are safe at every level independently. If the reversal event is replayed after Transaction 1 succeeded but before Transaction 3, only the missing transactions are created — the already-committed ones are skipped via idempotency.

---

## Scenario 12 — BaaS Deposit (external bank → customer account)

**Context:** Customer A receives a PIX from an external bank into their BaaS digital account. Money crosses the system boundary — the World account is used. This is the entry point of every real that will ever exist inside the ledger.

**Entity:** `customer-a` (BaaS Customer template)

**Inbound event:**
```json
{
  "event_type": "deposit.created",
  "event_id": "evt_120",
  "data": {
    "deposit_id": "dep_001",
    "entity_id": "customer-a",
    "amount": 1000.00,
    "currency": "BRL",
    "origin": "external_pix",
    "bank_reference": "PIX_IN_ABC123"
  }
}
```

**Entries posted:**

| # | Account              | Type   | Amount      | Key metadata               |
|---|----------------------|--------|-------------|----------------------------|
| 1 | 1.1.001 Checking     | debit  | R$1.000,00  | deposit_id: dep_001        |
| 2 | 9.9.999 World        | credit | R$1.000,00  | bank_reference: PIX_IN_ABC123 |

> **Balance check:** R$1.000 debits = R$1.000 credits ✓

**State after:**

| Account          | Balance     |
|------------------|-------------|
| Checking A       | +R$1.000,00 |
| World A          | −R$1.000,00 (credit balance: money entered from outside) |

> **Design note:** World's credit balance on the entity level is intentional — it records the total money that entered this entity from the external world. Σ World across all entities tracks the system's net exposure to the real world.

---

## Scenario 13 — Internal Transfer / PIX between BaaS customers

**Context:** Customer A sends R$300,00 to Customer B via PIX. Both are customers of the same BaaS platform. Money does **not** cross the system boundary — the Transfer account is used on both sides. Two ledger transactions are created and committed in a single DB transaction.

**Entities:** `customer-a` and `customer-b` (BaaS Customer template)

**Inbound event:**
```json
{
  "event_type": "transfer.created",
  "event_id": "evt_130",
  "data": {
    "transfer_id": "trf_001",
    "sender_entity_id": "customer-a",
    "receiver_entity_id": "customer-b",
    "amount": 300.00,
    "currency": "BRL",
    "description": "January Rent"
  }
}
```

Handler creates two transactions atomically. Both share `reference_id = "trf_001"`.

---

**Transaction A — customer-a (sender)** (`idempotency_key: "transfer:trf_001:customer-a"`)

| # | Account              | Type   | Amount     | Key metadata                        |
|---|----------------------|--------|------------|-------------------------------------|
| 1 | 9.9.998 Transfer     | debit  | R$300,00   | transfer_id: trf_001, to: customer-b |
| 2 | 1.1.001 Checking     | credit | R$300,00   | —                                   |

> R$300 left account A.

---

**Transaction B — customer-b (receiver)** (`idempotency_key: "transfer:trf_001:customer-b"`)

| # | Account              | Type   | Amount     | Key metadata                          |
|---|----------------------|--------|------------|---------------------------------------|
| 1 | 1.1.001 Checking     | debit  | R$300,00   | transfer_id: trf_001, from: customer-a |
| 2 | 9.9.998 Transfer     | credit | R$300,00   | —                                     |

> R$300 entered account B.

---

**State after:**

| Entity     | Account      | Balance     |
|------------|--------------|-------------|
| customer-a | Checking     | +R$700,00   |
| customer-a | Transfer     | +R$300,00 debit |
| customer-b | Checking     | +R$300,00   |
| customer-b | Transfer     | +R$300,00 credit |

**System-level invariant check:**

| | Transfer balance |
|---|---|
| customer-a | +R$300,00 (debit) |
| customer-b | −R$300,00 (credit) |
| **Σ Transfer** | **R$0,00 ✓** |

> **Design note:** The two transactions must be committed in a single DB transaction — partial success would leave the ledger in an inconsistent state (A debited, B not credited). Both transactions share `reference_id = "trf_001"` for full traceability. The Transfer account balance on each entity is the running total of internal money sent (debit) or received (credit) — a permanent, auditable record.

---

## Scenario 14 — BaaS Withdrawal (customer account → external bank)

**Context:** Customer A withdraws R$500,00 to their external bank account. Money crosses the system boundary — World is used. This is the exit point of money from the ledger.

**Inbound event:**
```json
{
  "event_type": "withdrawal.created",
  "event_id": "evt_140",
  "data": {
    "withdrawal_id": "wth_001",
    "entity_id": "customer-a",
    "amount": 500.00,
    "currency": "BRL",
    "destination": "external_ted",
    "bank_reference": "TED_OUT_XYZ789"
  }
}
```

**Entries posted:**

| # | Account          | Type   | Amount    | Key metadata                  |
|---|------------------|--------|-----------|-------------------------------|
| 1 | 9.9.999 World    | debit  | R$500,00  | bank_reference: TED_OUT_XYZ789 |
| 2 | 1.1.001 Checking | credit | R$500,00  | withdrawal_id: wth_001        |

> **Balance check:** R$500 debits = R$500 credits ✓

**State after:**

| Account      | Balance    |
|--------------|------------|
| Checking A   | +R$200,00  |
| World A      | R$500,00 debit (money exited to external world) |

> **Design note:** World's debit balance records total money that left this entity to the external world. Combined with Scenario 12, Customer A's World account now shows: R$1.000 credit (deposit) + R$500 debit (withdrawal) = R$500 net credit, meaning R$500 net entered the system for this entity and has not yet left.

---

## Scenario 15 — Full BaaS Lifecycle: Deposit → Transfer → Withdrawal

**Context:** Complete money journey for two customers: Customer A deposits R$1.000 from external bank, sends R$300 to Customer B internally, then withdraws R$500. This scenario traces every real from entry to exit.

**Entities:** `customer-a` (starting balance R$0), `customer-b` (starting balance R$0)

### Step 1 — Customer A deposits R$1.000 (Scenario 12)

| Entity     | Account  | Δ          | Balance     |
|------------|----------|------------|-------------|
| customer-a | Checking | +R$1.000   | R$1.000,00  |
| customer-a | World    | −R$1.000   | −R$1.000,00 |

### Step 2 — Customer A transfers R$300 to Customer B (Scenario 13)

| Entity     | Account  | Δ        | Balance     |
|------------|----------|----------|-------------|
| customer-a | Checking | −R$300   | R$700,00    |
| customer-a | Transfer | +R$300   | +R$300,00   |
| customer-b | Checking | +R$300   | R$300,00    |
| customer-b | Transfer | −R$300   | −R$300,00   |

### Step 3 — Customer A withdraws R$500 (Scenario 14)

| Entity     | Account  | Δ        | Balance     |
|------------|----------|----------|-------------|
| customer-a | Checking | −R$500   | R$200,00    |
| customer-a | World    | +R$500   | −R$500,00   |

### Final state

| Entity     | Account  | Balance     | Meaning                              |
|------------|----------|-------------|--------------------------------------|
| customer-a | Checking | R$200,00    | available                            |
| customer-a | Transfer | +R$300,00   | sent R$300 internally                |
| customer-a | World    | −R$500,00   | R$1.000 entered, R$500 exited (net −R$500) |
| customer-b | Checking | R$300,00    | available                            |
| customer-b | Transfer | −R$300,00   | received R$300 internally            |
| customer-b | World    | R$0,00      | no external movement                 |

**System-level audit:**

| Invariant | Value | Status |
|-----------|-------|--------|
| Σ Transfer (customer-a + customer-b) | R$300 − R$300 = **R$0** | ✓ |
| Σ World (customer-a + customer-b) | −R$1.000 + R$500 = −R$500 | = money still in the system |
| Σ Checking (customer-a + customer-b) | R$200 + R$300 = **R$500** | = exactly what should be in the system |

> **Design note:** The last row is the consistency proof: the R$500 sitting in Checking balances corresponds exactly to the R$1.000 that entered via World minus the R$500 that exited. The complete trace — which bank it came from, through whose hands it passed, to which bank it left — is in the entries without any join to external systems.
