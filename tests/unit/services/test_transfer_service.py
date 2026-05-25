from datetime import date
from decimal import Decimal
from unittest import TestCase
from unittest.mock import MagicMock
from uuid import uuid4

from src.exceptions.transfer import TransferAccountNotFoundError, TransferEntityNotFoundError
from src.model.chart_of_accounts import ChartOfAccounts
from src.model.constants.account_codes import ACC_RECEIVABLES, ACC_TRANSFER
from src.model.entity import Entity
from src.model.enums import AccountType
from src.model.schemas.transfers import TransferCreate
from src.model.transaction import Transaction
from src.services.transfer import TransferService


def _make_entity() -> Entity:
    entity = Entity(external_id=f"ext-{uuid4()}")
    entity.id = uuid4()
    return entity


def _make_account(entity_id, code: str, account_type=AccountType.ASSET) -> ChartOfAccounts:
    account = ChartOfAccounts(
        entity_id=entity_id,
        code=code,
        name=code,
        account_type=account_type,
        currency="BRL",
        current_balance=Decimal("1000.00"),
    )
    account.id = uuid4()
    return account


def _make_service():
    session = MagicMock()
    service = TransferService.__new__(TransferService)
    service._session = session
    service._entity_repo = MagicMock()
    service._account_repo = MagicMock()
    service._txn_repo = MagicMock()
    service._txn_svc = MagicMock()
    return service


def _make_payload(sender_id=None, receiver_id=None, amount="100.00") -> TransferCreate:
    return TransferCreate(
        sender_entity_id=sender_id or uuid4(),
        receiver_entity_id=receiver_id or uuid4(),
        amount=Decimal(amount),
        currency="BRL",
        effective_date=date(2026, 4, 21),
        description="test transfer",
    )


class TransferIdempotencyTest(TestCase):
    def setUp(self):
        self.service = _make_service()

    def test_returns_existing_when_both_keys_found(self):
        sender_txn = MagicMock(spec=Transaction)
        receiver_txn = MagicMock(spec=Transaction)
        self.service._txn_repo.get_by_idempotency_key.side_effect = [sender_txn, receiver_txn]

        payload = _make_payload()
        result = self.service.transfer(payload, "idem-key")

        self.assertEqual(result, (sender_txn, receiver_txn))
        self.service._txn_svc.post.assert_not_called()

    def test_proceeds_when_no_existing_keys(self):
        sender_entity_id = uuid4()
        receiver_entity_id = uuid4()
        self.service._txn_repo.get_by_idempotency_key.return_value = None
        self.service._entity_repo.exists.return_value = True
        self.service._account_repo.get_by_entity_and_code.return_value = MagicMock()

        sender_txn = MagicMock(spec=Transaction)
        sender_txn.id = uuid4()
        sender_txn.custom_data = {}
        receiver_txn = MagicMock(spec=Transaction)
        receiver_txn.id = uuid4()
        self.service._txn_svc.post.side_effect = [sender_txn, receiver_txn]

        payload = _make_payload(sender_id=sender_entity_id, receiver_id=receiver_entity_id)
        self.service.transfer(payload, "new-key")

        self.assertEqual(self.service._txn_svc.post.call_count, 2)


class TransferEntityValidationTest(TestCase):
    def setUp(self):
        self.service = _make_service()
        self.service._txn_repo.get_by_idempotency_key.return_value = None

    def test_raises_when_sender_entity_not_found(self):
        self.service._entity_repo.exists.return_value = False
        with self.assertRaises(TransferEntityNotFoundError):
            self.service.transfer(_make_payload(), "key")

    def test_raises_when_receiver_entity_not_found(self):
        self.service._entity_repo.exists.side_effect = [True, False]
        with self.assertRaises(TransferEntityNotFoundError):
            self.service.transfer(_make_payload(), "key")


class TransferAccountValidationTest(TestCase):
    def setUp(self):
        self.service = _make_service()
        self.service._txn_repo.get_by_idempotency_key.return_value = None
        self.service._entity_repo.exists.return_value = True

    def test_raises_when_sender_transfer_account_missing(self):
        self.service._account_repo.get_by_entity_and_code.return_value = None
        with self.assertRaises(TransferAccountNotFoundError):
            self.service.transfer(_make_payload(), "key")

    def test_raises_when_sender_checking_account_missing(self):
        # first call (sender Transfer) OK, second (sender Checking) missing
        self.service._account_repo.get_by_entity_and_code.side_effect = [MagicMock(), None]
        with self.assertRaises(TransferAccountNotFoundError):
            self.service.transfer(_make_payload(), "key")

    def test_raises_when_receiver_transfer_account_missing(self):
        # sender accounts OK, receiver Transfer missing
        self.service._account_repo.get_by_entity_and_code.side_effect = [
            MagicMock(), MagicMock(), None
        ]
        with self.assertRaises(TransferAccountNotFoundError):
            self.service.transfer(_make_payload(), "key")


class TransferEntriesTest(TestCase):
    def setUp(self):
        self.service = _make_service()
        self.service._txn_repo.get_by_idempotency_key.return_value = None
        self.service._entity_repo.exists.return_value = True
        self.service._account_repo.get_by_entity_and_code.return_value = MagicMock()

        self.sender_txn = MagicMock(spec=Transaction)
        self.sender_txn.id = uuid4()
        self.sender_txn.custom_data = {}
        self.receiver_txn = MagicMock(spec=Transaction)
        self.receiver_txn.id = uuid4()
        self.service._txn_svc.post.side_effect = [self.sender_txn, self.receiver_txn]

    def test_sender_entries_transfer_debit_checking_credit(self):
        payload = _make_payload(amount="100.00")
        self.service.transfer(payload, "key")

        sender_call_args = self.service._txn_svc.post.call_args_list[0]
        sender_txn_create = sender_call_args[0][1]
        entries = {e.account_code: e for e in sender_txn_create.entries}

        self.assertEqual(entries[ACC_TRANSFER].entry_type, "debit")
        self.assertEqual(entries[ACC_TRANSFER].amount, Decimal("100.00"))
        self.assertEqual(entries[ACC_RECEIVABLES].entry_type, "credit")
        self.assertEqual(entries[ACC_RECEIVABLES].amount, Decimal("100.00"))

    def test_receiver_entries_checking_debit_transfer_credit(self):
        payload = _make_payload(amount="100.00")
        self.service.transfer(payload, "key")

        receiver_call_args = self.service._txn_svc.post.call_args_list[1]
        receiver_txn_create = receiver_call_args[0][1]
        entries = {e.account_code: e for e in receiver_txn_create.entries}

        self.assertEqual(entries[ACC_RECEIVABLES].entry_type, "debit")
        self.assertEqual(entries[ACC_RECEIVABLES].amount, Decimal("100.00"))
        self.assertEqual(entries[ACC_TRANSFER].entry_type, "credit")
        self.assertEqual(entries[ACC_TRANSFER].amount, Decimal("100.00"))

    def test_transfer_net_across_entities_is_zero(self):
        payload = _make_payload(amount="250.00")
        self.service.transfer(payload, "key")

        sender_entries = self.service._txn_svc.post.call_args_list[0][0][1].entries
        receiver_entries = self.service._txn_svc.post.call_args_list[1][0][1].entries

        all_transfer_entries = [
            e for e in sender_entries + receiver_entries if e.account_code == ACC_TRANSFER
        ]
        debit_total = sum(e.amount for e in all_transfer_entries if e.entry_type == "debit")
        credit_total = sum(e.amount for e in all_transfer_entries if e.entry_type == "credit")
        self.assertEqual(debit_total, credit_total)

    def test_sender_idempotency_key_format(self):
        payload = _make_payload()
        self.service.transfer(payload, "my-key")

        sender_call = self.service._txn_svc.post.call_args_list[0]
        self.assertEqual(sender_call[0][2], "transfer:send:my-key")

    def test_receiver_idempotency_key_format(self):
        payload = _make_payload()
        self.service.transfer(payload, "my-key")

        receiver_call = self.service._txn_svc.post.call_args_list[1]
        self.assertEqual(receiver_call[0][2], "transfer:recv:my-key")

    def test_counterpart_linked_in_custom_data(self):
        sender_id = uuid4()
        receiver_id = uuid4()
        payload = _make_payload(sender_id=sender_id, receiver_id=receiver_id)
        self.service.transfer(payload, "key")

        receiver_call_args = self.service._txn_svc.post.call_args_list[1]
        receiver_txn_create = receiver_call_args[0][1]
        self.assertEqual(
            receiver_txn_create.custom_data["counterpart_entity_id"], str(sender_id)
        )
        self.assertEqual(
            receiver_txn_create.custom_data["counterpart_transaction_id"], str(self.sender_txn.id)
        )
