from src.exceptions.account import InvalidTemplateError
from src.model.chart_of_accounts import AccountType
from src.model.constants.account_codes import ACC_ANTICIPATION_FEE, ACC_RECEIVABLES, ACC_RECEIVABLES_ANTICIPATED
from src.model.schemas.accounts import AccountCreate

_COMMON = [
    AccountCreate(code="9.9.998", name="Transfer", account_type=AccountType.equity, currency="BRL"),
    AccountCreate(code="9.9.999", name="World", account_type=AccountType.equity, currency="BRL"),
]

_TEMPLATES: dict[str, list[AccountCreate]] = {
    "merchant": [
        AccountCreate(code=ACC_RECEIVABLES, name="Receivables", account_type=AccountType.asset, currency="BRL"),
        AccountCreate(code=ACC_RECEIVABLES_ANTICIPATED, name="Receivables Anticipated",
                      account_type=AccountType.asset, currency="BRL"),
        AccountCreate(code="1.2.001", name="Cash", account_type=AccountType.asset, currency="BRL"),
        AccountCreate(code="2.2.001", name="IOF Payable", account_type=AccountType.liability, currency="BRL"),
        AccountCreate(code="2.2.002", name="PIS/COFINS Payable", account_type=AccountType.liability, currency="BRL"),
        AccountCreate(code="2.2.003", name="CSLL/IRPJ Provision", account_type=AccountType.liability, currency="BRL"),
        AccountCreate(code="3.1.001", name="Revenue-Sales", account_type=AccountType.revenue, currency="BRL"),
        AccountCreate(code="4.1.001", name="Expense-MDR", account_type=AccountType.expense, currency="BRL"),
        AccountCreate(code="4.1.002", name="Expense-Platform", account_type=AccountType.expense, currency="BRL"),
        AccountCreate(code=ACC_ANTICIPATION_FEE, name="Expense-Anticipation",
                      account_type=AccountType.expense, currency="BRL"),
        AccountCreate(code="4.2.001", name="Expense-IOF", account_type=AccountType.expense, currency="BRL"),
        AccountCreate(code="4.2.002", name="Expense-PIS/COFINS", account_type=AccountType.expense, currency="BRL"),
        AccountCreate(code="4.2.003", name="Expense-CSLL/IRPJ", account_type=AccountType.expense, currency="BRL"),
    ],
    "customer": [
        AccountCreate(
            code="2.1.001", name="Payable to Counterparty", account_type=AccountType.liability, currency="BRL"
        ),
        AccountCreate(code="4.1.001", name="Expense-Purchases", account_type=AccountType.expense, currency="BRL"),
    ],
    "operator": [
        AccountCreate(code=ACC_RECEIVABLES, name="Receivables", account_type=AccountType.asset, currency="BRL"),
        AccountCreate(code="3.1.001", name="Revenue-Platform Fee", account_type=AccountType.revenue, currency="BRL"),
        AccountCreate(code="4.1.001", name="Expense-White-label Fee", account_type=AccountType.expense, currency="BRL"),
    ],
    "platform": [
        AccountCreate(code=ACC_RECEIVABLES, name="Receivables", account_type=AccountType.asset, currency="BRL"),
        AccountCreate(code="3.1.001", name="Revenue-Platform Fee", account_type=AccountType.revenue, currency="BRL"),
        AccountCreate(code="3.1.002", name="Revenue-White-label Fee", account_type=AccountType.revenue, currency="BRL"),
    ],
    "baas_customer": [
        AccountCreate(code="1.1.001", name="Checking Account", account_type=AccountType.asset, currency="BRL"),
        AccountCreate(code="1.1.002", name="Savings Account", account_type=AccountType.asset, currency="BRL"),
    ],
}


def get_template(name: str) -> list[AccountCreate]:
    template = _TEMPLATES.get(name)
    if template is None:
        raise InvalidTemplateError(f"Template '{name}' not found")
    return [*template, *_COMMON]
