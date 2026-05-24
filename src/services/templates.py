from src.exceptions.account import InvalidTemplateError
from src.model.chart_of_accounts import AccountType
from src.model.constants.account_codes import ACC_ANTICIPATION_FEE, ACC_RECEIVABLES, ACC_RECEIVABLES_ANTICIPATED
from src.model.enums import AccountTemplate, Currency
from src.model.schemas.accounts import AccountCreate

_COMMON = [
    AccountCreate(code="9.9.998", name="Transfer", account_type=AccountType.EQUITY, currency=Currency.BRL),
    AccountCreate(code="9.9.999", name="World", account_type=AccountType.EQUITY, currency=Currency.BRL),
]

_TEMPLATES: dict[AccountTemplate, list[AccountCreate]] = {
    AccountTemplate.MERCHANT: [
        AccountCreate(code=ACC_RECEIVABLES, name="Receivables", account_type=AccountType.ASSET, currency=Currency.BRL),
        AccountCreate(code=ACC_RECEIVABLES_ANTICIPATED, name="Receivables Anticipated",
                      account_type=AccountType.ASSET, currency=Currency.BRL),
        AccountCreate(code="1.2.001", name="Cash", account_type=AccountType.ASSET, currency=Currency.BRL),
        AccountCreate(code="2.2.001", name="IOF Payable", account_type=AccountType.LIABILITY, currency=Currency.BRL),
        AccountCreate(code="2.2.002", name="PIS/COFINS Payable",
                      account_type=AccountType.LIABILITY, currency=Currency.BRL),
        AccountCreate(code="2.2.003", name="CSLL/IRPJ Provision",
                      account_type=AccountType.LIABILITY, currency=Currency.BRL),
        AccountCreate(code="3.1.001", name="Revenue-Sales", account_type=AccountType.REVENUE, currency=Currency.BRL),
        AccountCreate(code="4.1.001", name="Expense-MDR", account_type=AccountType.EXPENSE, currency=Currency.BRL),
        AccountCreate(code="4.1.002", name="Expense-Platform", account_type=AccountType.EXPENSE, currency=Currency.BRL),
        AccountCreate(code=ACC_ANTICIPATION_FEE, name="Expense-Anticipation",
                      account_type=AccountType.EXPENSE, currency=Currency.BRL),
        AccountCreate(code="4.2.001", name="Expense-IOF", account_type=AccountType.EXPENSE, currency=Currency.BRL),
        AccountCreate(code="4.2.002", name="Expense-PIS/COFINS",
                      account_type=AccountType.EXPENSE, currency=Currency.BRL),
        AccountCreate(code="4.2.003", name="Expense-CSLL/IRPJ",
                      account_type=AccountType.EXPENSE, currency=Currency.BRL),
    ],
    AccountTemplate.CUSTOMER: [
        AccountCreate(
            code="2.1.001", name="Payable to Counterparty", account_type=AccountType.LIABILITY, currency=Currency.BRL
        ),
        AccountCreate(code="4.1.001", name="Expense-Purchases",
                      account_type=AccountType.EXPENSE, currency=Currency.BRL),
    ],
    AccountTemplate.OPERATOR: [
        AccountCreate(code=ACC_RECEIVABLES, name="Receivables", account_type=AccountType.ASSET, currency=Currency.BRL),
        AccountCreate(code="3.1.001", name="Revenue-Platform Fee",
                      account_type=AccountType.REVENUE, currency=Currency.BRL),
        AccountCreate(code="4.1.001", name="Expense-White-label Fee",
                      account_type=AccountType.EXPENSE, currency=Currency.BRL),
    ],
    AccountTemplate.PLATFORM: [
        AccountCreate(code=ACC_RECEIVABLES, name="Receivables", account_type=AccountType.ASSET, currency=Currency.BRL),
        AccountCreate(code="3.1.001", name="Revenue-Platform Fee",
                      account_type=AccountType.REVENUE, currency=Currency.BRL),
        AccountCreate(code="3.1.002", name="Revenue-White-label Fee",
                      account_type=AccountType.REVENUE, currency=Currency.BRL),
    ],
    AccountTemplate.BAAS_CUSTOMER: [
        AccountCreate(code="1.1.001", name="Checking Account", account_type=AccountType.ASSET, currency=Currency.BRL),
        AccountCreate(code="1.1.002", name="Savings Account", account_type=AccountType.ASSET, currency=Currency.BRL),
    ],
}


def get_template(name: AccountTemplate) -> list[AccountCreate]:
    template = _TEMPLATES.get(name)
    if template is None:
        raise InvalidTemplateError(f"Template '{name}' not found")
    return [*template, *_COMMON]
