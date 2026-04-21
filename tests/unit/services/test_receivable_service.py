from datetime import date
from decimal import Decimal
from unittest import TestCase
from unittest.mock import MagicMock
from uuid import uuid4

from src.exceptions.receivable import InvalidReceivableStatusTransitionError, ReceivableNotFoundError
from src.model.receivable import Receivable
from src.model.schemas.receivables import ReceivableCreate
from src.services.receivable import ReceivableService


def _make_service() -> ReceivableService:
    service = ReceivableService(MagicMock())
    service._repo = MagicMock()
    return service


def _make_receivable(status: str = "pending") -> Receivable:
    r = Receivable(
        entity_id=uuid4(),
        transaction_id=uuid4(),
        gross_amount=Decimal("100.00"),
        net_amount=Decimal("97.70"),
        fee_amount=Decimal("2.30"),
        status=status,
    )
    r.id = uuid4()
    return r


class RoundTest(TestCase):
    def setUp(self):
        self.service = _make_service()

    def test_rounds_half_up(self):
        self.assertEqual(self.service._round(Decimal("100.004")), Decimal("100.00"))

    def test_rounds_half_up_at_midpoint(self):
        self.assertEqual(self.service._round(Decimal("100.005")), Decimal("100.01"))

    def test_exact_value_unchanged(self):
        self.assertEqual(self.service._round(Decimal("97.70")), Decimal("97.70"))


class CreateTest(TestCase):
    def setUp(self):
        self.service = _make_service()

    def test_create_stores_rounded_amounts(self):
        payload = ReceivableCreate(
            gross_amount=Decimal("100.004"),
            net_amount=Decimal("97.704"),
            fee_amount=Decimal("2.304"),
        )
        entity_id = uuid4()
        transaction_id = uuid4()

        saved = Receivable(
            entity_id=entity_id,
            transaction_id=transaction_id,
            gross_amount=Decimal("100.00"),
            net_amount=Decimal("97.70"),
            fee_amount=Decimal("2.30"),
            status="pending",
        )
        self.service._repo.save.return_value = saved

        result = self.service.create(entity_id, transaction_id, payload)

        call_args = self.service._repo.save.call_args[0][0]
        self.assertEqual(call_args.gross_amount, Decimal("100.00"))
        self.assertEqual(call_args.net_amount, Decimal("97.70"))
        self.assertEqual(call_args.fee_amount, Decimal("2.30"))
        self.assertEqual(call_args.status, "pending")
        self.assertEqual(result, saved)

    def test_create_with_exact_amounts_stores_unchanged(self):
        payload = ReceivableCreate(
            gross_amount=Decimal("100.00"),
            net_amount=Decimal("97.70"),
            fee_amount=Decimal("2.30"),
        )
        entity_id = uuid4()
        transaction_id = uuid4()
        self.service._repo.save.return_value = MagicMock()

        self.service.create(entity_id, transaction_id, payload)

        call_args = self.service._repo.save.call_args[0][0]
        self.assertEqual(call_args.gross_amount, Decimal("100.00"))
        self.assertEqual(call_args.net_amount, Decimal("97.70"))
        self.assertEqual(call_args.fee_amount, Decimal("2.30"))

    def test_create_passes_expected_settlement_date(self):
        expected_date = date(2026, 5, 1)
        payload = ReceivableCreate(
            gross_amount=Decimal("100.00"),
            net_amount=Decimal("97.70"),
            fee_amount=Decimal("2.30"),
            expected_settlement_date=expected_date,
        )
        self.service._repo.save.return_value = MagicMock()

        self.service.create(uuid4(), uuid4(), payload)

        call_args = self.service._repo.save.call_args[0][0]
        self.assertEqual(call_args.expected_settlement_date, expected_date)

    def test_create_passes_custom_data(self):
        payload = ReceivableCreate(
            gross_amount=Decimal("100.00"),
            net_amount=Decimal("97.70"),
            fee_amount=Decimal("2.30"),
            custom_data={"key": "value"},
        )
        self.service._repo.save.return_value = MagicMock()

        self.service.create(uuid4(), uuid4(), payload)

        call_args = self.service._repo.save.call_args[0][0]
        self.assertEqual(call_args.custom_data, {"key": "value"})


class SettleTest(TestCase):
    def setUp(self):
        self.service = _make_service()

    def test_settle_pending_sets_status_and_date(self):
        receivable = _make_receivable("pending")
        self.service._repo.get_by_entity_and_id.return_value = receivable
        settlement_date = date(2026, 5, 1)

        result = self.service.settle(receivable.entity_id, receivable.id, settlement_date)

        self.assertEqual(result.status, "settled")
        self.assertEqual(result.actual_settlement_date, settlement_date)

    def test_settle_on_settled_raises(self):
        receivable = _make_receivable("settled")
        self.service._repo.get_by_entity_and_id.return_value = receivable

        with self.assertRaises(InvalidReceivableStatusTransitionError):
            self.service.settle(receivable.entity_id, receivable.id, date(2026, 5, 1))

    def test_settle_on_cancelled_raises(self):
        receivable = _make_receivable("cancelled")
        self.service._repo.get_by_entity_and_id.return_value = receivable

        with self.assertRaises(InvalidReceivableStatusTransitionError):
            self.service.settle(receivable.entity_id, receivable.id, date(2026, 5, 1))


class CancelTest(TestCase):
    def setUp(self):
        self.service = _make_service()

    def test_cancel_pending_sets_status(self):
        receivable = _make_receivable("pending")
        self.service._repo.get_by_entity_and_id.return_value = receivable

        result = self.service.cancel(receivable.entity_id, receivable.id)

        self.assertEqual(result.status, "cancelled")

    def test_cancel_on_settled_raises(self):
        receivable = _make_receivable("settled")
        self.service._repo.get_by_entity_and_id.return_value = receivable

        with self.assertRaises(InvalidReceivableStatusTransitionError):
            self.service.cancel(receivable.entity_id, receivable.id)


class GetByIdTest(TestCase):
    def setUp(self):
        self.service = _make_service()

    def test_get_by_id_returns_receivable(self):
        receivable = _make_receivable()
        self.service._repo.get_by_entity_and_id.return_value = receivable

        result = self.service.get_by_id(receivable.entity_id, receivable.id)

        self.assertEqual(result, receivable)

    def test_get_by_id_not_found_raises(self):
        self.service._repo.get_by_entity_and_id.return_value = None
        entity_id = uuid4()
        receivable_id = uuid4()

        with self.assertRaises(ReceivableNotFoundError):
            self.service.get_by_id(entity_id, receivable_id)


class ListByEntityTest(TestCase):
    def setUp(self):
        self.service = _make_service()

    def test_list_delegates_to_repo(self):
        entity_id = uuid4()
        expected = [_make_receivable(), _make_receivable()]
        self.service._repo.get_by_entity.return_value = expected

        result = self.service.list_by_entity(entity_id, status="pending")

        self.service._repo.get_by_entity.assert_called_once_with(entity_id, status="pending")
        self.assertEqual(result, expected)

    def test_list_without_status_delegates_to_repo(self):
        entity_id = uuid4()
        self.service._repo.get_by_entity.return_value = []

        result = self.service.list_by_entity(entity_id)

        self.service._repo.get_by_entity.assert_called_once_with(entity_id, status=None)
        self.assertEqual(result, [])
