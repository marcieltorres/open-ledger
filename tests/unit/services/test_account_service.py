from unittest import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.exceptions.account import AccountNotFoundError, InvalidTemplateError
from src.exceptions.entity import EntityNotFoundError
from src.model.chart_of_accounts import AccountType, ChartOfAccounts
from src.model.schemas.accounts import AccountCreate, AccountProvision, AccountUpdate
from src.services.account import AccountService


def _make_account(**kwargs) -> ChartOfAccounts:
    account = ChartOfAccounts(
        entity_id=kwargs.get("entity_id", uuid4()),
        code=kwargs.get("code", "1.1.001"),
        name=kwargs.get("name", "Receivables"),
        account_type=kwargs.get("account_type", AccountType.asset),
        currency=kwargs.get("currency", "BRL"),
    )
    account.id = kwargs.get("id", uuid4())
    return account


class AccountServiceProvisionTest(TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.service = AccountService(self.session)
        self.service._repo = MagicMock()
        self.service._entity_repo = MagicMock()

    def test_provision_with_template_calls_get_template(self):
        entity_id = uuid4()
        self.service._entity_repo.exists.return_value = True
        self.service._repo.get_by_entity_and_code.return_value = None
        self.service._repo.save.side_effect = lambda x: x

        with patch("src.services.account.get_template") as mock_get:
            mock_get.return_value = [
                AccountCreate(code="9.9.998", name="Transfer", account_type=AccountType.equity),
                AccountCreate(code="9.9.999", name="World", account_type=AccountType.equity),
            ]
            result = self.service.provision(entity_id, AccountProvision(template="merchant"))
            mock_get.assert_called_once_with("merchant")
            self.assertEqual(len(result), 2)

    def test_provision_with_inline_accounts(self):
        entity_id = uuid4()
        self.service._entity_repo.exists.return_value = True
        self.service._repo.get_by_entity_and_code.return_value = None
        self.service._repo.save.side_effect = lambda x: x

        result = self.service.provision(
            entity_id,
            AccountProvision(accounts=[
                AccountCreate(code="1.1.001", name="Receivables", account_type=AccountType.asset),
            ]),
        )
        self.assertEqual(len(result), 1)

    def test_provision_entity_not_found_raises(self):
        self.service._entity_repo.exists.return_value = False
        with self.assertRaises(EntityNotFoundError):
            self.service.provision(uuid4(), AccountProvision(template="merchant"))

    def test_provision_duplicate_is_idempotent(self):
        entity_id = uuid4()
        existing = _make_account(entity_id=entity_id)
        self.service._entity_repo.exists.return_value = True
        self.service._repo.get_by_entity_and_code.return_value = existing

        result = self.service.provision(
            entity_id,
            AccountProvision(accounts=[
                AccountCreate(code="1.1.001", name="Receivables", account_type=AccountType.asset),
            ]),
        )
        self.assertEqual(result, [existing])
        self.service._repo.save.assert_not_called()

    def test_provision_no_template_no_accounts_raises(self):
        self.service._entity_repo.exists.return_value = True
        with self.assertRaises(InvalidTemplateError):
            self.service.provision(uuid4(), AccountProvision())


class AccountServiceListTest(TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.service = AccountService(self.session)
        self.service._repo = MagicMock()
        self.service._entity_repo = MagicMock()

    def test_list_by_entity_returns_accounts(self):
        entity_id = uuid4()
        self.service._entity_repo.exists.return_value = True
        self.service._repo.get_by_entity.return_value = [_make_account(entity_id=entity_id)]
        result = self.service.list_by_entity(entity_id)
        self.assertEqual(len(result), 1)

    def test_list_by_entity_not_found_raises(self):
        self.service._entity_repo.exists.return_value = False
        with self.assertRaises(EntityNotFoundError):
            self.service.list_by_entity(uuid4())


class AccountServiceGetByIdTest(TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.service = AccountService(self.session)
        self.service._repo = MagicMock()
        self.service._entity_repo = MagicMock()

    def test_get_by_id_returns_account(self):
        entity_id = uuid4()
        account = _make_account(entity_id=entity_id)
        self.service._entity_repo.exists.return_value = True
        self.service._repo.get_by_id.return_value = account
        result = self.service.get_by_id(entity_id, account.id)
        self.assertEqual(result, account)

    def test_get_by_id_not_found_raises(self):
        self.service._entity_repo.exists.return_value = True
        self.service._repo.get_by_id.return_value = None
        with self.assertRaises(AccountNotFoundError):
            self.service.get_by_id(uuid4(), uuid4())

    def test_get_by_id_wrong_entity_raises(self):
        account = _make_account(entity_id=uuid4())
        self.service._entity_repo.exists.return_value = True
        self.service._repo.get_by_id.return_value = account
        with self.assertRaises(AccountNotFoundError):
            self.service.get_by_id(uuid4(), account.id)

    def test_get_by_id_entity_not_found_raises(self):
        self.service._entity_repo.exists.return_value = False
        with self.assertRaises(EntityNotFoundError):
            self.service.get_by_id(uuid4(), uuid4())


class AccountServiceUpdateTest(TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.service = AccountService(self.session)
        self.service._repo = MagicMock()
        self.service._entity_repo = MagicMock()

    def test_update_name(self):
        entity_id = uuid4()
        account = _make_account(entity_id=entity_id)
        self.service._entity_repo.exists.return_value = True
        self.service._repo.get_by_id.return_value = account
        self.service._repo.save.return_value = account
        self.service.update(entity_id, account.id, AccountUpdate(name="New Name"))
        self.assertEqual(account.name, "New Name")

    def test_update_not_found_raises(self):
        self.service._entity_repo.exists.return_value = True
        self.service._repo.get_by_id.return_value = None
        with self.assertRaises(AccountNotFoundError):
            self.service.update(uuid4(), uuid4(), AccountUpdate(name="X"))
