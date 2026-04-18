# Open Ledger — Especificação Completa

> **Nota:** Esta é a tradução oficial para o português brasileiro da especificação Open Ledger. O documento original em inglês em `.docs/open-ledger-full-spec.md` é a versão autoritativa.

---

## Visão Geral

Um ledger financeiro é o registro imutável e autoritativo de todos os eventos financeiros de um sistema. Cada saldo, cada taxa, cada transferência é rastreável até um lançamento específico. Este documento especifica o design do **Open Ledger**: um serviço de contabilidade de partidas dobradas construído como um microsserviço isolado, com seu próprio banco de dados, comunicando-se com o restante do sistema exclusivamente por meio de eventos.

O design é inspirado em implementações de ledger em produção do [Midaz](https://github.com/LerianStudio/midaz) e do [Formance](https://www.formance.com/).

---

## Princípios Fundamentais

### 1. Imutabilidade
Lançamentos nunca são atualizados ou excluídos. Correções são feitas postando novos lançamentos de estorno. O histórico completo é sempre preservado.

### 2. Contabilidade de Partidas Dobradas
Todo evento financeiro gera pelo menos um débito e um crédito de valor igual. Em transações de moeda única, a soma de todos os débitos é igual à soma de todos os créditos. Em transações multi-moeda, o invariante é aplicado **por moeda**: Σ débitos(moeda X) = Σ créditos(moeda X) para cada moeda presente na transação.

### 3. Cabeçalho de Transação + Lançamentos _(Midaz / Formance)_
Uma `transaction` é um cabeçalho que agrupa um ou mais `entries` relacionados (ex.: uma venda + taxa). Isso habilita transações multi-perna nativas e operações atômicas — ou todos os lançamentos são confirmados ou nenhum é.

Status suportados: `pending` (pendente), `committed` (confirmado), `voided` (cancelado).

### 4. Saldo Corrente Incremental _(Midaz)_
Cada conta mantém uma coluna `current_balance` atualizada pela camada de aplicação dentro da mesma transação de banco de dados que insere os lançamentos. Leituras de saldo são um `SELECT` direto — nenhuma agregação é necessária. Um job noturno recalcula os saldos do zero e alerta sobre qualquer divergência maior que R$0,01.

### 5. Contas de Fronteira do Sistema _(Formance)_
A faixa `9.9.xxx` é reservada para contas de fronteira do sistema. Duas são criadas automaticamente para cada entidade:

**`9.9.999 Mundo`** — fronteira externa genérica. Representa o mundo exterior quando a contraparte específica de liquidação não importa ou ainda não é conhecida. Usado como fallback para implantações simples.

**`9.9.998 Transferência`** — representa dinheiro cruzando fronteiras de entidades *dentro* do ledger, sem sair do sistema. Usado para transferências internas entre entidades (ex.: PIX entre dois clientes BaaS na mesma plataforma).

Para implantações operacionais que exigem conciliação bancária, `9.9.999 Mundo` deve ser substituído por contas Mundo tipificadas — uma por contraparte de liquidação externa — seguindo a mesma convenção `9.9.xxx`:

| Código  | Nome              | Representa                                            |
|---------|-------------------|-------------------------------------------------------|
| 9.9.901 | Mundo/STR         | Banco Central STR — TED e transferências de alto valor |
| 9.9.902 | Mundo/CIP-PIX     | CIP — liquidação PIX                                  |
| 9.9.903 | Mundo/COMPE       | COMPE — câmara de compensação de cheques (D+1)        |
| 9.9.904 | Mundo/Banco-{cod} | Banco liquidante nomeado (uma conta por banco)         |
| 9.9.999 | Mundo             | Fallback genérico para casos simples ou desconhecidos  |

O handler de eventos deve resolver a subconta Mundo correta no momento do lançamento — a rede de liquidação é conhecida a partir da instrução de pagamento. Esta é uma decisão da camada do ledger: determina qual conta recebe o lançamento e não pode ser corrigida retroativamente em uma camada upstream.

Invariantes de nível de sistema:
- Σ todas as contas `9.9.9xx Mundo` em todas as entidades = dinheiro líquido que entrou ou saiu do sistema.
- Σ `9.9.998 Transferência` em todas as entidades = **0** sempre — todo envio tem um recebimento correspondente dentro do ledger.

### 6. Event Sourcing Parcial _(Formance)_
Todo evento de entrada é registrado em uma tabela `event_log` antes do processamento. O estado materializado (contas, saldos) é derivado do processamento desses eventos. Eventos com falha podem ser reprocessados. Isso não é event sourcing puro — o estado materializado é a fonte de verdade para leituras.

### 7. Metadados Ricos
Cada `transaction` e cada `entry` individual carrega um campo `metadata JSONB`. Taxas, fórmulas e referências externas são armazenadas no ponto de cálculo, sem recomputação posterior.

### 8. Multi-Tenant
Cada entidade tem seu próprio conjunto isolado de contas. Uma entidade é qualquer participante do sistema financeiro — um lojista, um cliente, um operador de plataforma, ou qualquer outra coisa. O ledger não impõe uma taxonomia de tipo: `entity_type` é metadado livre, não uma restrição estrutural. Entidades são registradas a partir de eventos — o ledger nunca lê do banco de dados do serviço upstream.

### 9. Multi-Moeda
Cada conta é denominada em uma única moeda (`currency CHAR(3)`, ISO 4217). Lançamentos devem corresponder à moeda da conta em que são postados — isso é aplicado pela aplicação. Conversões entre moedas usam um par de contas de trânsito FX de moeda única como intermediários, mantendo as partidas dobradas íntegras por moeda. A taxa de câmbio é capturada em `metadata` no momento do lançamento e nunca recomputada.

### 10. Arquitetura em Camadas — O Que Pertence ao Ledger

O ledger é a fonte autoritativa de lançamentos financeiros, mas é um componente em uma plataforma financeira mais ampla. Camadas upstream — sejam um data warehouse, um pipeline analítico, um serviço de relatórios, ou qualquer outra arquitetura que uma equipe escolha — consomem dados do ledger para produzir agregações, cálculos e relatórios que seria inadequado embutir no núcleo contábil.

**O critério de decisão:**

> Se uma decisão deve ser tomada no momento do lançamento — ela determina *qual conta* debitar/creditar, *quanto*, ou *se* um lançamento é permitido — ela pertence ao ledger.
> Se pode ser derivada depois do fato a partir de dados já presentes no ledger, pertence a uma camada upstream.

```
┌──────────────────────────────────────────────────────────────┐
│  CAMADAS UPSTREAM                                            │
│  (serviço de relatórios, data warehouse, pipeline analítico, │
│   camada de submissão regulatória — arquitetura é escolha    │
│   da equipe)                                                 │
│                                                              │
│  Responsável por: balancete, DRE, relatórios COSIF, cálculo  │
│  de PDD, motor de competência, motor fiscal, conciliação     │
├──────────────────────────────────────────────────────────────┤
│  LEDGER                                                      │
│  Responsável por: lançamentos imutáveis, saldos de contas,   │
│  event log, idempotência, guardas de período, contas suspense│
└──────────────────────────────────────────────────────────────┘
```

**Aplicado a funcionalidades financeiras comuns:**

| Funcionalidade | Onde | Motivo |
|---|---|---|
| Qual conta de liquidação usar (STR vs CIP-PIX) | Ledger | Determina a conta no momento do lançamento |
| Conta suspense para recursos não alocados | Ledger | Dinheiro chegou — deve ser balanceado imediatamente |
| Guarda de período (rejeitar lançamentos em períodos fechados) | Ledger | Deve ser aplicado na fonte autoritativa |
| Lançamento de imposto (par débito/crédito IOF) | Ledger | O lançamento em si; o cálculo é upstream |
| Cálculo de taxa × base do IOF | Upstream | Calculado antes do lançamento, resultado enviado como evento |
| Cálculo da provisão PDD | Upstream | Classificação de risco → posta evento ao ledger |
| Balancete | Upstream | Agregação sobre dados existentes no ledger |
| Relatório regulatório COSIF | Upstream | Mapeamento + formatação sobre dados agregados |

O ledger não calcula impostos, juros, provisões ou risco. Ele recebe os resultados desses cálculos como eventos padrão de débito/crédito e os registra.

---

## Modelo de Dados

### Schema

```sql
-- ============================================================
-- ENTIDADES
-- Registro local de entidades upstream. Populado a partir de eventos.
-- entity_type é metadado livre (ex.: 'merchant', 'customer') —
-- não é uma restrição estrutural e não tem CHECK.
-- ============================================================
CREATE TABLE entities (
  id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  external_id      VARCHAR(255) NOT NULL,        -- ID no sistema upstream (qualquer formato)
  name             VARCHAR(255),                 -- rótulo legível por humanos
  parent_entity_id UUID         REFERENCES entities(id),  -- NULL = raiz; FK auto-referenciada para hierarquia multi-nível
  is_active        BOOLEAN      DEFAULT true,
  metadata         JSONB,                        -- entity_type e quaisquer outros atributos aqui
  created_at       TIMESTAMP    DEFAULT NOW(),

  UNIQUE (external_id)
);

-- ============================================================
-- PLANO DE CONTAS
-- Um conjunto de contas por entidade, criado a partir de templates.
-- ============================================================
CREATE TABLE chart_of_accounts (
  id                UUID     PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_id         UUID     NOT NULL REFERENCES entities(id),

  code              VARCHAR(20)  NOT NULL,   -- ex.: '1.1.001'
  name              VARCHAR(255) NOT NULL,   -- ex.: 'Contas a Receber'
  account_type      VARCHAR(20)  NOT NULL,   -- asset | liability | revenue | expense | equity
  category          VARCHAR(50),             -- dica de classificação estrutural para relatórios downstream
                                             -- (ex.: 'current_assets', 'tax_liabilities', 'processing_fees')
                                             -- não tem efeito no comportamento de lançamento
  currency          CHAR(3)      NOT NULL DEFAULT 'BRL',  -- ISO 4217; cada conta mantém uma moeda

  -- Saldo incremental (inspirado no Midaz)
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
-- TRANSAÇÕES
-- Cabeçalho agrupando lançamentos relacionados em uma operação atômica.
-- ============================================================
CREATE TABLE transactions (
  id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_id        UUID         NOT NULL REFERENCES entities(id),
  -- Data de competência, não a data de lançamento.
  -- Um job executando em 02/01/2026 postando competência do dia anterior define effective_date = 2026-01-01.
  -- É assim que o ledger suporta regime de competência sem nenhuma lógica própria de accrual.
  effective_date   DATE         NOT NULL,

  transaction_type VARCHAR(50)  NOT NULL,                   -- 'sale', 'anticipation', 'settlement', 'accrual', 'tax_provision', ...
  -- pending  → lançamentos existem mas NÃO atualizam current_balance (aplicação pula atualização de saldo)
  -- committed → lançamentos impactam saldo; este é o padrão para a maioria dos eventos
  -- voided   → somente alcançável a partir de pending; apenas atualização de status, nenhum lançamento postado,
  --            saldo não é afetado pois lançamentos pending nunca o tocaram.
  --            Use para cancelamentos "nunca aconteceu" antes do commit.
  --            Para estornos de transações committed, poste uma nova transação com lançamentos espelhados.
  status           VARCHAR(20)  DEFAULT 'committed',

  -- Referência ao evento / objeto originador no sistema upstream
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
-- LANÇAMENTOS DE TRANSAÇÃO
-- Pernas individuais de débito/crédito de uma transação.
-- ============================================================
CREATE TABLE transaction_entries (
  id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  transaction_id UUID         NOT NULL REFERENCES transactions(id) ON DELETE RESTRICT,
  account_id     UUID         NOT NULL REFERENCES chart_of_accounts(id),

  entry_type     VARCHAR(10)  NOT NULL,   -- 'debit' | 'credit'
  amount         DECIMAL(20,2) NOT NULL,
  currency       CHAR(3)      NOT NULL,   -- deve corresponder a chart_of_accounts.currency para account_id (aplicado pela app)
  metadata       JSONB,
  created_at     TIMESTAMP    DEFAULT NOW(),

  CHECK (amount > 0),
  CHECK (entry_type IN ('debit', 'credit'))
);

-- ============================================================
-- LOG DE EVENTOS
-- Trilha de auditoria completa de todo evento de entrada.
-- ============================================================
CREATE TABLE event_log (
  id                  BIGSERIAL    PRIMARY KEY,
  event_type          VARCHAR(100) NOT NULL,
  event_id            VARCHAR(255) NOT NULL,  -- ID da mensagem do broker (chave de deduplicação)
  source              VARCHAR(50)  DEFAULT 'upstream',
  aggregate_id        UUID,
  aggregate_type      VARCHAR(50),
  payload             JSONB        NOT NULL,
  status              VARCHAR(20)  DEFAULT 'received', -- received | processing | processed | failed | skipped
  error_message       TEXT,
  transaction_id      UUID,
  -- Populado após processamento. Um elemento por lançamento postado.
  -- Fornece um snapshot de auditoria autocontido — sem joins necessários para entender o que mudou.
  -- Estrutura:
  -- [
  --   {
  --     "account_id":    "uuid",
  --     "account_code":  "1.1.001",
  --     "account_name":  "Contas a Receber",
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
-- RECEBÍVEIS
-- Direito financeiro (direito creditório) nascido de um evento de venda.
-- Rastreia o ciclo de vida do recebível na perspectiva do ledger:
-- quando foi criado, seu detalhamento bruto/líquido/taxa, e quando liquida.
--
-- Estado específico de produto (ex.: detalhes de antecipação, cadeia de cessão)
-- pertence ao serviço de produto, que referencia receivables.id.
-- ============================================================
CREATE TABLE receivables (
  id                       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_id                UUID         NOT NULL REFERENCES entities(id),
  transaction_id           UUID         NOT NULL REFERENCES transactions(id),  -- transação de venda originadora
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
-- SNAPSHOTS DE SALDO
-- Snapshots diários por conta para consultas históricas.
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
-- ÍNDICES
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
-- PERÍODOS CONTÁBEIS
-- Controla quais períodos estão abertos para lançamento.
-- O ledger rejeita qualquer transação cujo effective_date caia
-- em um período fechado ou bloqueado. Este é o guarda autoritativo
-- — o status do período é aplicado na fonte de verdade, não nas
-- camadas upstream.
--
-- Transições de status:
--   open → closed  (fechamento normal de fim de mês)
--   closed → open  (reabertura autorizada para correções)
--   closed → locked (após submissão regulatória — irreversível)
--   locked → *     (não permitido; correções devem ser postadas no
--                   período aberto atual como estornos)
-- ============================================================
CREATE TABLE accounting_periods (
  id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  period_date DATE         NOT NULL,   -- primeiro dia do mês: 2025-12-01 = Dezembro 2025
  status      VARCHAR(20)  NOT NULL DEFAULT 'open',
  opened_at   TIMESTAMP    DEFAULT NOW(),
  closed_at   TIMESTAMP,
  locked_at   TIMESTAMP,
  closed_by   VARCHAR(100),
  locked_by   VARCHAR(100),
  notes       TEXT,                    -- motivo para reabertura ou bloqueio
  created_at  TIMESTAMP    DEFAULT NOW(),

  UNIQUE (period_date),
  CHECK (status IN ('open', 'closed', 'locked'))
);

CREATE INDEX idx_periods_status ON accounting_periods(status) WHERE status = 'open';
CREATE INDEX idx_periods_date   ON accounting_periods(period_date DESC);
```

---

## Recebíveis e a Fronteira com o Serviço de Produto

Um recebível (tabela `receivables`) é um **direito financeiro** (direito creditório) — um instrumento financeiro de primeira classe que representa o direito do lojista de receber um valor específico em uma data específica. É uma entidade legítima do ledger: tem identidade, um detalhamento bruto/líquido/taxa, e um ciclo de vida de liquidação (`pending → settled | cancelled`).

O que o ledger **não** modela é como os produtos operam sobre recebíveis. O produto de antecipação, por exemplo, precisa rastrear a taxa de antecipação, o número de dias antecipados e a fórmula de cálculo da taxa. Esse estado pertence ao **serviço de antecipação**, que referencia `receivables.id` e posta lançamentos ao ledger via eventos.

**Regra de fronteira:** se um campo descreve o que aconteceu com um recebível (liquidado na data X, cancelado pelo evento Y), pertence ao ledger. Se descreve como um produto o processou (antecipado a 1,5% por 20 dias), pertence ao serviço de produto.

```
Ledger (open-ledger)          Serviço de produto (ex.: serviço-antecipacao)
─────────────────────         ──────────────────────────────────────────────
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

O serviço de antecipação posta dois eventos ao ledger quando processa um recebível: um que move o saldo de `1.1.001 Contas a Receber` para `1.1.002 Contas a Receber Antecipadas`, e um na liquidação que zera `1.1.002` via Mundo. O ledger registra os lançamentos; o serviço de produto detém o estado de negócio.

---

## Mapeamento Regulatório

O mapeamento regulatório (COSIF, FINREP, PCEC, etc.) é responsabilidade da **camada upstream de relatórios**, não do ledger. Aplicando o [critério de arquitetura em camadas](#10-arquitetura-em-camadas--o-que-pertence-ao-ledger): o código COSIF de uma conta nunca é necessário no momento do lançamento — só é necessário ao gerar um relatório regulatório. Esse cálculo ocorre após o fato, sobre dados já presentes no ledger.

O ledger usa códigos internos de conta em formato livre (`1.1.001`, `3.1.001`, etc.) otimizados para clareza e flexibilidade. A camada upstream de relatórios regulatórios mantém o mapeamento de códigos internos para códigos de framework, com seu próprio versionamento para lidar com atualizações ao longo do tempo.

### COSIF (Brasil)

Toda instituição regulada pelo Banco Central do Brasil — IP, IFP, SCD, SEP ou banco — é obrigada a usar o **Plano Contábil das Instituições do Sistema Financeiro Nacional (COSIF)**. O COSIF define um plano de contas hierárquico mandatório no formato `X.X.X.XX-D` (onde D é um dígito verificador). A camada upstream de relatórios traduz os códigos de conta do ledger para códigos COSIF ao submeter ao BACEN.

**Mapeamento de referência — template Lojista (ilustrativo):**

| Código interno | Nome interno        | Código COSIF | Nome COSIF (abreviado)                             |
|----------------|---------------------|--------------|----------------------------------------------------|
| 1.1.001        | Contas a Receber    | 1.8.9.90-1   | Outros Créditos — Direitos por Serv. Prestados     |
| 1.2.001        | Caixa               | 1.1.5.00-1   | Disponibilidades — Depósitos Bancários             |
| 3.1.001        | Receita - Vendas    | 7.6.9.00-0   | Rendas de Serviços — Outras                        |
| 4.1.001        | Despesa - Taxa MDR  | 8.7.9.00-9   | Despesas de Serviços — Outras                      |

> **Importante:** os códigos acima são ilustrativos. Os códigos COSIF exatos dependem do tipo de entidade (IP vs. banco vs. SCD) e devem ser validados contra a publicação oficial do BACEN.

### Outros frameworks

O mesmo padrão upstream se aplica a outros frameworks regulatórios:

| Framework | Regulador          | Aplicável a                           |
|-----------|--------------------|---------------------------------------|
| `COSIF`   | BACEN (Brasil)     | IPs, IFPs, SCDs, SEPs, bancos         |
| `FINREP`  | EBA (UE)           | Instituições de crédito da UE         |
| `PCEC`    | ACP (França)       | Instituições de crédito francesas     |
| `GAAP`    | FASB (EUA)         | Entidades dos EUA (voluntário)        |

---

## Contabilidade Tributária

O ledger **registra** lançamentos tributários — não os calcula. O cálculo de impostos (alíquota, base, regime aplicável) é responsabilidade de um serviço fiscal dedicado. O ledger recebe o resultado como um par padrão de débito/crédito e o lança como qualquer outro lançamento.

### Regra de fronteira

| Responsabilidade | Responsável |
|---|---|
| Calcular alíquota IOF × base × fator de tempo | Serviço fiscal |
| Determinar regime PIS/COFINS (cumulativo vs. não-cumulativo) | Serviço fiscal |
| Calcular estimativa mensal CSLL/IRPJ | Serviço fiscal |
| Postar os lançamentos resultantes de débito/crédito | Ledger |
| Manter saldos de passivos fiscais | Ledger (via plano de contas) |

### Como os lançamentos tributários chegam ao ledger

**IOF** — calculado por operação, postado atomicamente com a transação originadora. O handler de eventos chama o serviço fiscal antes de postar os lançamentos; o lançamento de IOF é incluído na mesma transação de BD:

| # | Conta                        | Tipo   | Valor  | metadata                               |
|---|------------------------------|--------|--------|----------------------------------------|
| 1 | 4.2.001 Despesa - IOF        | débito | R$0,08 | `{"tax_type":"IOF","rate":0.000082}`  |
| 2 | 2.2.001 IOF a Recolher       | crédito| R$0,08 | `{"triggers_transaction_id":"txn_123"}`|

**PIS/COFINS** — postado no fechamento mensal por um job fiscal como uma transação dedicada `transaction_type: "tax_provision"`.

**CSLL/IRPJ** — postado no fechamento trimestral (com estimativas mensais) pelo mesmo job fiscal.

### Contas tributárias

Contas relacionadas a impostos seguem o padrão abaixo e são incluídas nos templates de entidade para instituições reguladas:

| Faixa de código | Natureza | Exemplos |
|---|---|---|
| `2.2.xxx` | Passivos fiscais (a Recolher / Provisão) | IOF a Recolher, PIS/COFINS a Recolher, Provisão CSLL/IRPJ |
| `4.2.xxx` | Despesas tributárias | Despesa - IOF, Despesa - PIS/COFINS, Despesa - CSLL/IRPJ |

---

## Contabilidade de Competência

O ledger suporta regime de competência nativamente — ele não o implementa. A distinção importa:

- **O ledger fornece:** `effective_date` (data de competência) em cada transação, lançamentos imutáveis e garantias de idempotência.
- **O ledger não fornece:** cálculo de juros, cronogramas de amortização, convenções de contagem de dias, ou qualquer regra sobre quando o accrual deve ocorrer.

Um motor externo de competência (tipicamente parte do serviço de produto de crédito) é responsável por determinar quanta receita ou despesa acumulou em um dado dia e postá-la como um evento padrão. O ledger registra os lançamentos resultantes.

### Como os lançamentos de competência chegam ao ledger

O job de accrual roda diariamente, calcula o accrual de cada instrumento e posta um evento por instrumento com `effective_date` definido para a data de competência — não a data de posting. Se o job roda às 01:00 de 2 de janeiro para accruals de 1º de janeiro, `effective_date = 2026-01-01` e `created_at = 2026-01-02T01:00:00Z`.

**Exemplo — um dia de accrual de juros em uma operação de crédito (R$10.000 a 2% a.m.):**

| # | Conta                              | Tipo    | Valor   | metadata                                           |
|---|------------------------------------|---------|---------|----------------------------------------------------|
| 1 | 1.3.001 Juros a Receber            | débito  | R$6,45  | `{"instrument_id":"loan_abc","accrual_date":"2026-01-01","rate":0.02,"days":1}` |
| 2 | 3.2.001 Receita - Rendas de Juros  | crédito | R$6,45  | `{"method":"252_business_days"}`                   |

Quando o caixa entra (pagamento de juros):

| # | Conta                              | Tipo    | Valor   |
|---|------------------------------------|---------|---------|
| 1 | 1.2.001 Caixa                      | débito  | R$6,45  |
| 2 | 1.3.001 Juros a Receber            | crédito | R$6,45  |

### Idempotência para jobs periódicos

O `idempotency_key` em `transactions` previne duplo lançamento se o job de accrual reintentar. A convenção é:

```
accrual:{instrument_id}:{effective_date}
```

Se o job rodar duas vezes para o mesmo instrumento e data, a segunda tentativa bate na restrição UNIQUE em `idempotency_key` e é rejeitada — sem lançamentos duplicados.

### Contas de competência

Entidades com produtos de crédito devem incluir estas contas em seu plano:

| Código  | Nome                          | Tipo      | Categoria         |
|---------|-------------------------------|-----------|-------------------|
| 1.3.001 | Juros a Receber               | asset     | accrued_revenue   |
| 2.3.001 | Rendas a Apropriar            | liability | deferred_revenue  |
| 3.2.001 | Receita - Rendas de Juros     | revenue   | financial_revenue |
| 3.2.002 | Receita - Rendas de Tarifas   | revenue   | financial_revenue |

> `Rendas a Apropriar` é usado em operações de desconto onde os juros são recebidos antecipadamente e reconhecidos diariamente ao longo da vida do instrumento. `Juros a Receber` é usado em modelos de juros pós-pagos onde o caixa entra posteriormente.

---

## PDD — Provisão para Devedores Duvidosos

A **Resolução CMN nº 2.682** exige que as instituições financeiras classifiquem toda operação de crédito por nível de risco (AA a H) e mantenham provisões obrigatórias de perdas contra a carteira de crédito. Os percentuais de provisionamento variam de 0% (AA) a 100% (H).

Seguindo o [princípio de arquitetura em camadas](#10-arquitetura-em-camadas--o-que-pertence-ao-ledger):

- **Camada upstream:** classificação de risco por operação (AA→H), cálculo do valor de provisão necessário por faixa de rating, decisão de upgrade ou downgrade de classificação.
- **Ledger:** registra o lançamento de provisão resultante (constituição ou reversão) como uma transação padrão `transaction_type: "pdd_provision"` ou `"pdd_reversal"`.

### Lançamentos de PDD

**Constituição de provisão** (risco aumentado ou novo crédito classificado):

| # | Conta                           | Tipo    | Valor    | metadata                                              |
|---|---------------------------------|---------|----------|-------------------------------------------------------|
| 1 | 4.3.001 Despesa - PDD           | débito  | R$500,00 | `{"instrument_id":"loan_abc","rating":"D","rate":0.30}` |
| 2 | 1.6.002 PDD - Provisão          | crédito | R$500,00 | `{"resolution":"CMN_2682"}`                           |

`1.6.002 PDD - Provisão` é uma conta retificadora de ativo (allowance) — carrega saldo credor e é apresentada como dedução da carteira de crédito no balanço patrimonial.

**Reversão de provisão** (crédito promovido, quitado ou baixado):

| # | Conta                           | Tipo    | Valor    |
|---|---------------------------------|---------|----------|
| 1 | 1.6.002 PDD - Provisão          | débito  | R$500,00 |
| 2 | 4.3.001 Despesa - PDD           | crédito | R$500,00 |

### Contas de PDD

Entidades com carteiras de crédito devem incluir estas contas:

| Código  | Nome                  | Tipo    | Categoria         |
|---------|-----------------------|---------|-------------------|
| 1.6.001 | Carteira de Crédito   | asset   | credit_operations |
| 1.6.002 | PDD - Provisão        | asset   | credit_operations |
| 4.3.001 | Despesa - PDD         | expense | credit_expenses   |

> `1.6.002` usa `account_type: "asset"` com saldo credor permanente (negativo líquido). Este é o tratamento padrão de conta retificadora — o valor líquido da carteira de crédito é `1.6.001 + 1.6.002`.

---

## Contas de Suspense

Uma conta de suspense mantém recursos que chegaram ao sistema mas cuja alocação final ainda não é conhecida. Diferente das transações `pending` — que representam eventos que podem ou não acontecer — lançamentos de suspense representam dinheiro que **chegou e deve ser balanceado imediatamente**.

### Suspense vs. pending

| | Transação `pending` | Conta de suspense |
|---|---|---|
| Dinheiro no sistema? | Não necessariamente | Sim — recursos recebidos |
| Impacta `current_balance`? | Não | Sim |
| Usado quando | Evento ainda pode ser cancelado | Destino desconhecido ou timing bloqueado |
| Resolvido por | Confirmar ou cancelar a transação | Postar lançamento de liberação na conta correta |

### Quando contas de suspense são usadas

- **Corte de janela de liquidação:** recursos TED ou COMPE chegam após o fechamento da janela de liquidação (STR fecha às 17h30); a IP tem o dinheiro mas não pode repassá-lo até a próxima janela.
- **Contraparte não identificada:** um PIX é recebido mas a entidade de destino não pode ser vinculada a nenhuma conta conhecida.
- **Divergência de valor:** recursos recebidos não correspondem à instrução de liquidação esperada; retidos até que a conciliação confirme a alocação correta.

A decisão de mover recursos para fora do suspense — vinculação, conciliação, identificação da contraparte — pertence à camada upstream. O ato de registrar que os recursos chegaram e estão aguardando alocação pertence ao ledger.

### Convenção de contas de suspense

A faixa `9.8.xxx` é reservada para contas de suspense, uma por modalidade de liquidação:

| Código  | Nome                | Usado quando                                     |
|---------|---------------------|--------------------------------------------------|
| 9.8.001 | Suspense/STR        | TED/transferências de alto valor fora da janela STR |
| 9.8.002 | Suspense/CIP-PIX    | PIX com destino não identificado                  |
| 9.8.003 | Suspense/COMPE      | Float de cheque pendente de compensação COMPE    |

### Lançamentos de suspense

**Captura de recursos no suspense** (TED recebido, janela STR fechada, destino desconhecido):

| # | Conta                      | Tipo    | Valor       | metadata                                           |
|---|----------------------------|---------|-------------|---------------------------------------------------|
| 1 | 1.2.001 Caixa              | débito  | R$100.000   | `{"bank_ref":"TED_98765","received_at":"17:35"}` |
| 2 | 9.8.001 Suspense/STR       | crédito | R$100.000   | `{"reason":"post_cutoff","window_reopens":"next_business_day"}` |

**Liberação do suspense** (próximo dia útil, destino identificado):

| # | Conta                         | Tipo    | Valor     |
|---|-------------------------------|---------|-----------|
| 1 | 9.8.001 Suspense/STR          | débito  | R$100.000 |
| 2 | [conta destino da entidade]   | crédito | R$100.000 |

A convenção de `idempotency_key` para liberações de suspense é `suspense_release:{bank_ref}` para prevenir dupla alocação caso o job de conciliação upstream reintente.

---

## Fechamento de Período

### O que pertence ao ledger

O ledger detém o **guarda de período**: qualquer transação cujo `effective_date` caia em um período fechado ou bloqueado é rejeitada no momento do lançamento. Isso deve ser aplicado na fonte autoritativa — uma camada upstream não pode substituir essa verificação.

O ledger também **registra** lançamentos de encerramento (ex.: zerando contas de receita e despesa no Resultado do Exercício) quando são postados como eventos padrão `transaction_type: "period_closing"`. Não os calcula.

### O que pertence à camada upstream

A camada upstream é responsável por:
- Calcular o balancete do período
- Determinar o resultado líquido (receitas − despesas)
- Gerar e postar eventos de lançamentos de encerramento ao ledger
- Produzir DRE e balanços patrimoniais a partir dos dados do ledger
- Submeter relatórios regulatórios (COSIF/BACEN) após o período ser bloqueado

### Transições de status do período

```
open ──fechamento de mês──▶ closed ──submissão regulatória──▶ locked
         ▲                     │
         └──reabertura (auth)──┘
         (períodos locked não podem ser reabertos;
          correções devem ser postadas no período aberto atual)
```

| Status   | Novos lançamentos permitidos? | Pode ser reaberto? |
|----------|-------------------------------|---------------------|
| `open`   | Sim                           | N/A                 |
| `closed` | Não                           | Sim (autorizado)    |
| `locked` | Não                           | Não                 |

### Correções em períodos fechados

Uma vez fechado um período, correções de lançamentos dentro dele devem ser postadas no **período aberto atual** como transações de estorno (`transaction_type: "reversal"`) com `effective_date` definido para hoje. Antedatação ao período fechado não é permitida.

Uma vez que um período é **bloqueado** (submissão regulatória feita), isso é permanente e irreversível. A mesma regra de correção se aplica, com o requisito adicional de que a justificativa do estorno deve ser capturada em `transactions.description` para fins de auditoria.

### Exemplo de lançamento de encerramento

A camada upstream calcula o resultado líquido de dezembro de 2025 (Receita R$500k − Despesas R$320k = R$180k) e posta:

| # | Conta                                | Tipo    | Valor     |
|---|--------------------------------------|---------|-----------|
| 1 | 3.1.001 Receita - Vendas             | débito  | R$500.000 |
| 2 | 4.1.001 Despesa - Taxa MDR           | crédito | R$320.000 |
| 3 | 2.4.001 Resultado do Exercício       | crédito | R$180.000 |

`effective_date = 2025-12-31`, `transaction_type = "period_closing"`, `idempotency_key = "period_closing:2025-12"`.

---

## Plano de Contas

O Plano de Contas é o conjunto de contas pertencentes a uma única entidade. É totalmente flexível: uma entidade pode ter qualquer número de contas, com quaisquer nomes e tipos que se adequem à sua realidade financeira. Não há estrutura imposta — uma entidade simples pode ter três contas; uma complexa pode ter dezenas.

Um **template** é um Plano de Contas pré-definido usado como ponto de partida ao registrar uma nova entidade. Templates são uma conveniência, não uma restrição. Você pode aplicá-lo como está, estendê-lo ou construir um plano do zero.

Os cinco tipos de conta disponíveis são `asset` (ativo), `liability` (passivo), `revenue` (receita), `expense` (despesa) e `equity` (patrimônio). O código da conta (ex.: `1.1.001`) é de formato livre — use qualquer convenção de numeração que faça sentido para seu sistema.

### Template de Referência: Lojista

Este template é usado como a entidade de referência em todos os exemplos de fluxo de transação abaixo.

| Código  | Nome                            | Tipo      | Categoria           | Moeda |
|---------|---------------------------------|-----------|---------------------|-------|
| 1.1.001 | Contas a Receber                | asset     | current_assets      | BRL   |
| 1.1.002 | Contas a Receber Antecipadas    | asset     | current_assets      | BRL   |
| 1.2.001 | Caixa                           | asset     | cash                | BRL   |
| 2.2.001 | IOF a Recolher                  | liability | tax_liabilities     | BRL   |
| 2.2.002 | PIS/COFINS a Recolher           | liability | tax_liabilities     | BRL   |
| 2.2.003 | Provisão CSLL/IRPJ              | liability | tax_liabilities     | BRL   |
| 3.1.001 | Receita - Vendas                | revenue   | operating_revenue   | BRL   |
| 4.1.001 | Despesa - Taxa MDR              | expense   | processing_fees     | BRL   |
| 4.1.002 | Despesa - Taxa de Plataforma    | expense   | platform_fees       | BRL   |
| 4.1.003 | Despesa - Taxa de Antecipação   | expense   | financial_fees      | BRL   |
| 4.2.001 | Despesa - IOF                   | expense   | tax_expenses        | BRL   |
| 4.2.002 | Despesa - PIS/COFINS            | expense   | tax_expenses        | BRL   |
| 4.2.003 | Despesa - CSLL/IRPJ             | expense   | tax_expenses        | BRL   |
| 9.9.998 | Transferência                   | equity    | internal            | BRL   |
| 9.9.999 | Mundo                           | equity    | external            | BRL   |

> Para lojistas operando em múltiplas moedas, provisione um conjunto de contas por moeda (ex.: `1.1.001/BRL` e `1.1.001/USD`). A convenção de código de conta é de formato livre — use o que fizer sentido para seu sistema.

### Template de Referência: Cliente

Um plano mais simples para uma entidade que principalmente incorre em obrigações a pagar. Incluído para ilustrar que o mesmo ledger pode servir ambos os lados de uma transação com estruturas de contas completamente diferentes.

| Código  | Nome                            | Tipo      | Categoria           | Moeda |
|---------|---------------------------------|-----------|---------------------|-------|
| 2.1.001 | Obrigações com Contraparte      | liability | current_liabilities | BRL   |
| 4.1.001 | Despesa - Compras               | expense   | cost_of_goods       | BRL   |
| 9.9.998 | Transferência                   | equity    | internal            | BRL   |
| 9.9.999 | Mundo                           | equity    | external            | BRL   |

### Template de Referência: Operador

Para operadores white-label (nível Company B em uma hierarquia payfac). Coleta taxas de plataforma de sub-lojistas e paga uma taxa white-label upstream para a plataforma raiz.

| Código  | Nome                               | Tipo    | Categoria         | Moeda |
|---------|------------------------------------|---------|-------------------|-------|
| 1.1.001 | Contas a Receber                   | asset   | current_assets    | BRL   |
| 3.1.001 | Receita - Taxa de Plataforma       | revenue | operating_revenue | BRL   |
| 4.1.001 | Despesa - Taxa White-label         | expense | platform_fees     | BRL   |
| 9.9.998 | Transferência                      | equity  | internal          | BRL   |
| 9.9.999 | Mundo                              | equity  | external          | BRL   |

### Template de Referência: Plataforma

Para a entidade plataforma raiz (nível Fintech A). Recebe tanto taxas de plataforma diretas (de lojistas que possui diretamente) quanto taxas white-label (de operadores abaixo dela).

| Código  | Nome                               | Tipo    | Categoria         | Moeda |
|---------|------------------------------------|---------|-------------------|-------|
| 1.1.001 | Contas a Receber                   | asset   | current_assets    | BRL   |
| 3.1.001 | Receita - Taxa de Plataforma       | revenue | operating_revenue | BRL   |
| 3.1.002 | Receita - Taxa White-label         | revenue | operating_revenue | BRL   |
| 9.9.998 | Transferência                      | equity  | internal          | BRL   |
| 9.9.999 | Mundo                              | equity  | external          | BRL   |

### Template de Referência: Cliente BaaS

Para usuários finais de um produto Banking-as-a-Service (titulares de conta digital). A conta corrente é um ativo na perspectiva do cliente; o BaaS deve o saldo ao cliente.

| Código  | Nome             | Tipo   | Categoria      | Moeda |
|---------|------------------|--------|----------------|-------|
| 1.1.001 | Conta Corrente   | asset  | current_assets | BRL   |
| 1.1.002 | Conta Poupança   | asset  | current_assets | BRL   |
| 9.9.998 | Transferência    | equity | internal       | BRL   |
| 9.9.999 | Mundo            | equity | external       | BRL   |

### Contas de Fronteira do Sistema

A faixa `9.9.xxx` é reservada para contas de fronteira do sistema. `9.9.999 Mundo` e `9.9.998 Transferência` são criadas para cada entidade. Para implantações operacionais, `Mundo` deve ser sub-tipificado por contraparte de liquidação (veja o [Princípio Fundamental 5](#5-contas-de-fronteira-do-sistema-formance)).

| Evento                              | Débito           | Crédito          |
|-------------------------------------|------------------|------------------|
| Depósito via PIX                    | Conta Corrente   | Mundo/CIP-PIX    |
| Depósito via TED                    | Conta Corrente   | Mundo/STR        |
| Saque via PIX                       | Mundo/CIP-PIX    | Conta Corrente   |
| Saque via TED                       | Mundo/STR        | Conta Corrente   |
| Transferência interna — remetente   | Transferência    | Conta Corrente   |
| Transferência interna — recebedor   | Conta Corrente   | Transferência    |
| Chargeback (dinheiro retorna)       | Conta Corrente   | Mundo/CIP-PIX    |
| Liquidação / repasse bancário       | Mundo/Banco-{n}  | Contas a Receber |

**Rastreando dinheiro pelo sistema:**

```
Banco externo ──depósito──▶ [Mundo ▶ Conta Corrente]  entidade A
                                          │
                              [Transferência ▶ Transferência]  A → B (interno)
                                                           │
                                     [Conta Corrente ▶ Mundo] ──saque──▶ Banco externo
```

Todo real que entra no ledger via Mundo deve eventualmente sair via Mundo (ou permanecer como saldo). Todo débito em Transferência de uma entidade tem um crédito exato em Transferência de outra. A jornada completa de cada unidade de moeda é rastreável sem joins a sistemas externos.

---

## Fluxos de Transação

Todos os valores monetários abaixo usam USD para clareza. Os mesmos padrões se aplicam a qualquer moeda.

### Exemplo 1 — Venda ($100,00, MDR 2%, taxa de plataforma 0,3%)

> **MDR (Merchant Discount Rate):** a taxa cobrada por uma credenciadora em cada transação de cartão.

**Evento de entrada:**
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

**Lançamentos postados (6 pernas balanceadas):**

| # | Conta                              | Tipo    | Valor   | Metadado chave                     |
|---|------------------------------------|---------|---------|------------------------------------|
| 1 | 1.1.001 Contas a Receber           | débito  | $100,00 | transaction_id: txn_123            |
| 2 | 3.1.001 Receita - Vendas           | crédito | $100,00 | transaction_id: txn_123            |
| 3 | 4.1.001 Despesa - MDR              | débito  |   $2,00 | mdr_rate: 0.02, formula: "100×0.02"|
| 4 | 1.1.001 Contas a Receber           | crédito |   $2,00 | —                                  |
| 5 | 4.1.002 Despesa - Plataforma       | débito  |   $0,30 | platform_fee_rate: 0.003           |
| 6 | 1.1.001 Contas a Receber           | crédito |   $0,30 | —                                  |

> **Verificação de equilíbrio:** $102,30 total débitos = $102,30 total créditos ✓  
> **Resultado:** Lojista tem $97,70 em Contas a Receber.

---

### Exemplo 2 — Antecipação de Recebível

**Cenário:** Lojista tem $97,70 a receber em 30/12/2025 e solicita pagamento antecipado em 10/12/2025. Taxa de antecipação: 1,5% = $1,47.

**Evento de entrada:**
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

**Lançamentos postados:**

| # | Conta                                      | Tipo    | Valor  | Metadado chave                       |
|---|--------------------------------------------|---------|--------|--------------------------------------|
| 1 | 1.1.002 Contas a Receber Antecipadas       | débito  | $97,70 | anticipation_id: ant_456             |
| 2 | 1.1.001 Contas a Receber                   | crédito | $97,70 | original_settlement_date: 2025-12-30 |
| 3 | 4.1.003 Despesa - Taxa de Antecipação      | débito  |  $1,47 | rate: 0.015, days_advanced: 20       |
| 4 | 1.1.002 Contas a Receber Antecipadas       | crédito |  $1,47 | formula: "97.70 × 0.015"             |

> **Resultado:** Lojista tem $96,23 em Contas a Receber Antecipadas.

---

### Exemplo 3 — Liquidação (com Conta Mundo)

**Cenário:** O valor antecipado é liquidado — caixa transferido para a conta bancária do lojista e sai do sistema.

**Evento de entrada:**
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

**Lançamentos postados:**

| # | Conta                                   | Tipo    | Valor   | Metadado chave                      |
|---|-----------------------------------------|---------|---------|-------------------------------------|
| 1 | 9.9.999 Mundo                           | débito  | $96,23  | bank_reference: WIRE_12345          |
| 2 | 1.1.002 Contas a Receber Antecipadas    | crédito | $96,23  | settlement_date: 2025-12-10         |

> **Verificação de equilíbrio:** $96,23 total débitos = $96,23 total créditos ✓  
> **Resultado:** Contas a Receber Antecipadas está zerada. Conta Mundo mostra $96,23 saindo do sistema.

---

### Exemplo 4 — Estorno

Um estorno desfaz uma transação `committed` postando uma nova transação com lançamentos espelhados. O ledger não modela *por que* o estorno aconteceu — chargeback, reembolso, correção de erro — isso é lógica de negócio upstream capturada em `metadata`. A única preocupação do ledger é que todo lançamento da transação original seja compensado.

> Este exemplo assume que a venda do Exemplo 1 ainda não foi liquidada (Contas a Receber = $97,70). Para estornos pós-liquidação, os mesmos lançamentos se aplicam mas contas como Mundo precisam refletir recursos retornando do sistema externo.

**Evento de entrada:**
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

**Lançamentos postados (espelho do Exemplo 1):**

| # | Conta                              | Tipo    | Valor   | Metadado chave                              |
|---|------------------------------------|---------|---------|---------------------------------------------|
| 1 | 3.1.001 Receita - Vendas           | débito  | $100,00 | reversal_id: rev_999, reason: chargeback    |
| 2 | 1.1.001 Contas a Receber           | crédito | $100,00 | —                                           |
| 3 | 1.1.001 Contas a Receber           | débito  |   $2,00 | reversal: mdr_fee                           |
| 4 | 4.1.001 Despesa - MDR              | crédito |   $2,00 | —                                           |
| 5 | 1.1.001 Contas a Receber           | débito  |   $0,30 | reversal: platform_fee                      |
| 6 | 4.1.002 Despesa - Plataforma       | crédito |   $0,30 | —                                           |

> **Verificação de equilíbrio:** $102,30 total débitos = $102,30 total créditos ✓  
> **Resultado:** Todas as contas retornam a $0. Receita, MDR e lançamentos de taxa de plataforma estão totalmente compensados.

---

## Estratégia de Saldo

### Abordagem híbrida _(inspirada no Midaz)_

| Camada                       | Como funciona                                                                    | Propósito                          |
|------------------------------|-----------------------------------------------------------------------------------|------------------------------------|
| **Saldo incremental**        | Aplicação atualiza `current_balance` dentro da mesma transação de BD             | Leituras instantâneas (< 5ms)      |
| **Recálculo noturno**        | Job em background soma todos os lançamentos por conta, compara com `current_balance` | Validação de consistência       |
| **Snapshot diário**          | Job tira snapshot de todos os saldos de conta às 02:00 UTC                       | Consultas históricas / time-travel |

### Atualização de saldo gerenciada pela aplicação

`current_balance` é mantido pela aplicação, não por um trigger de banco de dados. Todas as atualizações de saldo acontecem dentro da mesma transação de banco de dados que insere os lançamentos — se algo falhar, toda a operação é revertida atomicamente.

Antes de confirmar, a aplicação valida as partidas dobradas por moeda:

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

Para cada lançamento sendo postado, a aplicação deve:
1. `SELECT ... FOR UPDATE` na linha da conta afetada (adquire lock de linha, serializando escritas concorrentes na mesma conta)
2. Calcular o delta usando a fórmula abaixo
3. `UPDATE current_balance` e incrementar `balance_version`

```python
# pseudocódigo — roda dentro da mesma transação de BD que insere os lançamentos
for entry in entries:
    account = session.execute(
        select(Account)
        .where(Account.id == entry.account_id)
        .with_for_update()           # lock de linha
    ).scalar_one()

    delta = entry.amount if is_normal_side(account.account_type, entry.entry_type) else -entry.amount

    account.current_balance += delta
    account.balance_version += 1
    account.last_entry_at = now()
```

`balance_version` é um contador de mudanças — incrementado a cada atualização de saldo. O job de validação noturna o usa para detectar contas que foram modificadas fora do fluxo esperado.

### Fórmula de saldo por tipo de conta

| Tipo de conta                        | Lado normal (crescimento) | Fórmula                   |
|--------------------------------------|---------------------------|---------------------------|
| `asset` / `expense`                  | débito                    | Σ débitos − Σ créditos    |
| `liability` / `revenue` / `equity`   | crédito                   | Σ créditos − Σ débitos    |

Transações `pending` **nunca** atualizam `current_balance` — a atualização de saldo é completamente ignorada até que a transação seja confirmada.

### Metas de desempenho

| Operação              | Meta    |
|-----------------------|---------|
| Leitura de saldo      | < 5ms   |
| Extrato mensal        | < 500ms |
| Balanço patrimonial   | < 1s    |

---

## API de Extrato

O extrato é uma visão formatada sobre os lançamentos de uma determinada entidade e intervalo de datas.

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
      "description": "Venda #txn_123",
      "movements": [
        { "account": "Contas a Receber", "entry_type": "debit",  "amount": 100.00 },
        { "account": "Receita - Vendas", "entry_type": "credit", "amount": 100.00 }
      ],
      "balance_after": 100.00
    }
  ]
}
```

Lógica de geração:
1. **Saldo inicial** — `current_balance` ou snapshot do dia anterior ao início do período.
2. **Movimentos** — todos os lançamentos no intervalo de datas, ordenados por `created_at`.
3. **Saldo corrente** — acumulado por movimento.

---

## Arquitetura Orientada a Eventos

```
┌──────────────────┐
│  SERVIÇO UPSTREAM│
│  Processa op.    │
│  Salva no BD     │
└────────┬─────────┘
         │ publica evento
         ▼
┌──────────────────┐
│  MESSAGE BROKER  │
│  (Kafka / SQS)   │
└────────┬─────────┘
         │ consumido por
         ▼
┌──────────────────────────┐
│    SERVIÇO DE LEDGER     │
│  1. Escreve no event_log │
│  2. Cria transação       │
│  3. Posta lançamentos    │
│  4. App atualiza saldo   │
└──────────────────────────┘
```

### Registro de entidade e provisionamento de contas

Registro de entidade e criação de contas são **responsabilidades separadas**. Uma entidade pode existir no ledger sem contas — as contas são provisionadas explicitamente, seja no momento do registro ou posteriormente conforme as necessidades da entidade evoluem.

O evento `entity.created` suporta três modos:

**Opção A — atalho de template** (recomendado para casos padrão)
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
O ledger aplica o template nomeado e cria todas as contas definidas nele.

**Opção B — contas inline** (para estruturas personalizadas)
```json
{
  "event_type": "entity.created",
  "data": {
    "entity_id": "abc-123",
    "name": "ACME Store",
    "accounts": [
      { "code": "1.1.001", "name": "Contas a Receber", "account_type": "asset"  },
      { "code": "9.9.999", "name": "Mundo",             "account_type": "equity" }
    ]
  }
}
```

**Opção C — apenas registrar, adicionar contas depois**
```json
{
  "event_type": "entity.created",
  "data": { "entity_id": "abc-123", "name": "ACME Store" }
}
```
A entidade é registrada sem contas. Um evento subsequente `accounts.created` as adiciona. Isso suporta entidades cuja estrutura de contas não é conhecida no momento do registro, ou que evoluem ao longo do tempo (ex.: um lojista que habilita antecipação posteriormente recebe `Contas a Receber Antecipadas` adicionada sem precisar se re-registrar).

Se um evento financeiro chegar para uma entidade sem conta correspondente, o handler deve rejeitá-lo com um erro claro — nunca crie contas implicitamente.

### Hierarquia de entidades e cascata de taxas

Entidades formam uma árvore via `parent_entity_id`. A profundidade é arbitrária. `NULL` = raiz (a própria plataforma).

```
fintech-a           (parent = NULL)        ← raiz
├── merchant-direct  (parent = fintech-a)  ← lojista direto, sem operador
├── company-b        (parent = fintech-a)  ← operador white-label
│   ├── merchant-b1  (parent = company-b)
│   └── merchant-b2  (parent = company-b)
└── company-c        (parent = fintech-a)
    └── merchant-c1  (parent = company-c)
```

**Regra de cascata de taxas:** ao processar uma transação para um lojista, o handler percorre `parent_entity_id` até `NULL`, criando uma transação de ledger por ancestral que tem um acordo de taxa com o filho. O ledger não aplica regras de taxa — isso é lógica de aplicação orientada pela árvore de entidades.

**Consultando a árvore completa** (CTE recursiva):

```sql
WITH RECURSIVE entity_tree AS (
  -- âncora: começa a partir de qualquer nó
  SELECT id, name, parent_entity_id, 0 AS depth
  FROM entities
  WHERE id = :root_id

  UNION ALL

  -- recursão: desce um nível por iteração
  SELECT e.id, e.name, e.parent_entity_id, et.depth + 1
  FROM entities e
  JOIN entity_tree et ON e.parent_entity_id = et.id
)
SELECT * FROM entity_tree ORDER BY depth;
```

### Fluxo de processamento

1. Serviço upstream publica evento com payload completo.
2. Ledger escreve o evento bruto em `event_log` com `status = received`.
3. Handler busca a entidade usando `event.data.entity_id` → `entities.external_id`; se não encontrada, a registra.
4. Handler cria o cabeçalho da `transaction`.
5. Handler insere todos os `entries` em uma única operação atômica.
6. Aplicação atualiza `current_balance` em cada conta afetada via `SELECT FOR UPDATE` dentro da mesma transação.
7. Handler atualiza `receivables` se aplicável.
8. Handler marca a linha do `event_log` como `processed`.
9. Em caso de falha: marca como `failed`, evento é reintentado com backoff exponencial.

### Tipos de eventos suportados

| Evento                   | Gatilho                                    | Ação do ledger                                          |
|--------------------------|--------------------------------------------|---------------------------------------------------------|
| `entity.created`         | Nova entidade registrada upstream          | Registra entidade; opcionalmente provisiona contas      |
| `accounts.created`       | Contas adicionadas a entidade existente    | Cria contas a partir de template ou definição inline    |
| `transaction.created`    | Nova venda                                 | Posta lançamentos de venda + taxa                       |
| `anticipation.created`   | Solicitação de pagamento antecipado        | Reclassifica recebível + posta taxa de antecipação      |
| `settlement.completed`   | Recursos desembolsados                     | Posta débito Mundo + crédito Contas a Receber           |
| `deposit.created`        | Dinheiro entra do banco externo            | Posta crédito Mundo + débito Conta Corrente             |
| `withdrawal.created`     | Dinheiro sai para banco externo            | Posta crédito Conta Corrente + débito Mundo             |
| `transfer.created`       | Transferência interna entre entidades      | Posta Transferência+Conta Corrente no remetente; Conta Corrente+Transferência no recebedor — duas transações vinculadas, um commit de BD |
| `transaction.voided`     | Cancelado antes do commit                  | Define status → `voided`; sem lançamentos; saldo inalterado |
| `transaction.reversed`   | Estorno pós-commit (qualquer motivo)       | Posta nova transação com lançamentos espelhados         |

### Idempotência

Há dois mecanismos independentes de deduplicação com escopos diferentes:

| Mecanismo | Tabela | Escopo | Protege contra |
|---|---|---|---|
| `UNIQUE (event_id, event_type)` | `event_log` | Nível de mensagem | Broker entregando a mesma mensagem duas vezes |
| `UNIQUE (idempotency_key)` | `transactions` | Nível de operação de negócio | Upstream reintentando com novo ID de mensagem para a mesma operação |

As duas camadas são necessárias porque a deduplicação do `event_log` só captura a mesma mensagem chegando duas vezes. Se o upstream re-publica a mesma operação de negócio com um novo `event_id` (ex.: uma retentativa que gera uma nova mensagem no broker), o `event_log` deixa passar — `idempotency_key` é a última linha de defesa.

**Gerando `idempotency_key`**

A chave deve ser derivada dos dados de negócio, não do `event_id`:

```
idempotency_key = "{transaction_type}:{reference_id}"
```

Exemplos:
- `"sale:txn_123"`
- `"anticipation:ant_456"`
- `"settlement:settle_789"`

Isso garante que não importa quantos eventos cheguem para a mesma operação upstream, apenas uma transação de ledger seja criada.

---

## Multi-Moeda

### Regras

1. Cada conta mantém exatamente uma moeda (`chart_of_accounts.currency`).
2. Cada lançamento registra sua moeda (`transaction_entries.currency`).
3. A aplicação aplica: `entry.currency == account.currency`. Postar um lançamento em USD em uma conta BRL é rejeitado.
4. As partidas dobradas são validadas por moeda, não globalmente.

### Padrão de conversão FX

Uma conversão de moeda usa duas **contas de trânsito FX** de moeda única como intermediários. Cada conta de trânsito é denominada em uma moeda e deve resultar em zero após cada ciclo completo de conversão.

**Exemplo:** cliente converte $100,00 USD → BRL à taxa de 5,20.

Contas provisionadas para a entidade:
| Código  | Nome              | Tipo   | Moeda |
|---------|-------------------|--------|-------|
| 1.1.010 | Contas a Receber  | asset  | USD   |
| 1.1.011 | Contas a Receber  | asset  | BRL   |
| 5.1.001 | Trânsito FX       | equity | USD   |
| 5.1.002 | Trânsito FX       | equity | BRL   |

**Transação 1 — lado USD** (fecha a posição USD):

| # | Conta                | Tipo    | Valor        | Metadado chave                  |
|---|----------------------|---------|--------------|---------------------------------|
| 1 | 1.1.010 Recv USD     | crédito | $100,00 USD  | fx_rate: 5.20, par: BRL         |
| 2 | 5.1.001 FX-USD       | débito  | $100,00 USD  | conversion_id: conv_001         |

> Partidas dobradas USD: $100 débitos = $100 créditos ✓

**Transação 2 — lado BRL** (abre a posição BRL):

| # | Conta                | Tipo    | Valor         | Metadado chave                  |
|---|----------------------|---------|---------------|---------------------------------|
| 1 | 5.1.002 FX-BRL       | crédito | R$520,00 BRL  | conversion_id: conv_001         |
| 2 | 1.1.011 Recv BRL     | débito  | R$520,00 BRL  | fx_rate: 5.20, par: USD         |

> Partidas dobradas BRL: R$520 débitos = R$520 créditos ✓

Após ambas as transações, as contas de Trânsito FX resultam em zero (USD: $100 débito cancelado pelo crédito; BRL: R$520 crédito cancelado pelo débito). A taxa de câmbio e a fórmula são armazenadas em `metadata` — nunca recomputadas.

### Ganho / perda FX

Se a taxa de conversão diferir da taxa pela qual a obrigação original foi registrada (ex.: uma fatura precificada a uma taxa, liquidada a outra), a diferença é postada em contas dedicadas de ganho/perda:

| Código  | Nome            | Tipo    | Moeda |
|---------|-----------------|---------|-------|
| 3.2.001 | Ganho FX        | revenue | BRL   |
| 4.2.001 | Perda FX        | expense | BRL   |

O lançamento de ganho/perda é adicionado como uma perna extra à Transação 2, mantendo o lado BRL balanceado.

---

## Arredondamento

Todos os cálculos monetários usam **arredondamento HALF_UP para 2 casas decimais**, aplicado independentemente por moeda.

- `$97,70 × 0,015 = $1,4655` → arredonda para **`$1,47`**
- Este é o padrão usado por processadores de pagamento (Stripe, Adyen) e é a regra mais auditável: qualquer valor terminando em 5 sempre arredonda para cima, sem exceções.
- HALF_EVEN (arredondamento bancário) foi considerado mas rejeitado — produz resultados contraintuitivos (`$1,4655 → $1,46`) difíceis de explicar a usuários e auditores.
- Para moedas sem casas decimais (ex.: JPY), use `Decimal('1')` como constante de precisão em vez de `Decimal('0.01')`.

**Em Python**, sempre use `decimal.Decimal` — nunca `float`. Aritmética de ponto flutuante é binária e não pode representar a maioria das frações decimais exatamente (`0.1 + 0.2 = 0.30000000000000004`), o que quebra verificações de equilíbrio de partidas dobradas em escala.

```python
from decimal import Decimal, ROUND_HALF_UP

PRECISION = Decimal('0.01')

def round_amount(value: Decimal) -> Decimal:
    return value.quantize(PRECISION, rounding=ROUND_HALF_UP)
```

---

## Requisitos Técnicos

- **PostgreSQL 13+** — JSONB, índices GIN, `gen_random_uuid()`
- **Message broker** — Kafka, RabbitMQ ou SNS+SQS
- **Redis** — opcional, recomendado para cache de saldos quentes
- **PgBouncer** — pool de conexões para escritas de alto throughput

---

## Estratégia de Testes

### Testes unitários (cobertura 100% obrigatória)
- Validação de saldo débito/crédito por transação
- Corretude da fórmula de saldo por tipo de conta
- Comportamento de atualização de `current_balance` gerenciado pela aplicação
- Idempotência em eventos duplicados
- Geração de lançamento na conta Mundo

### Testes de integração
- Fluxo completo: venda → liquidação (com conta Mundo)
- Fluxo de antecipação
- Cancelamento / estorno de chargeback
- Replay de evento (reprocessar um evento `failed`)
- Transações multi-perna

### Testes de carga
- 1.000 transações/segundo com múltiplos lançamentos cada
- Leitura de saldo com 1M+ lançamentos no histórico da conta
- Extrato mensal com 10K+ movimentos
- Validação noturna em 100K+ contas

---

## Referências

- [Accounting for Computer Scientists — Martin Kleppmann](https://martin.kleppmann.com/2011/03/07/accounting-for-computer-scientists.html)
- [Event Sourcing — Martin Fowler](https://martinfowler.com/eaaDev/EventSourcing.html)
- [Midaz Ledger](https://github.com/LerianStudio/midaz) — modelo de transação, estratégia de saldo incremental
- [Formance Ledger](https://www.formance.com/) — conta Mundo, event sourcing, metadados ricos
- [Modern Treasury — What is a ledger database?](https://www.moderntreasury.com/learn/what-is-a-ledger-database)
- [Double-Entry Bookkeeping — Wikipedia](https://en.wikipedia.org/wiki/Double-entry_bookkeeping)
