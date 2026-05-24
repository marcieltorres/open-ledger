from uuid import UUID

from sqlalchemy.orm import Session

from src.exceptions.transfer import TransferAccountNotFoundError, TransferEntityNotFoundError
from src.model.constants.account_codes import ACC_RECEIVABLES, ACC_TRANSFER
from src.model.entity import Entity
from src.model.enums import EntryType, TransactionType
from src.model.schemas.transactions import TransactionCreate, TransactionEntryCreate
from src.model.schemas.transfers import TransferCreate
from src.model.transaction import Transaction
from src.repositories.account import AccountRepository
from src.repositories.base import BaseRepository
from src.repositories.transaction import TransactionRepository
from src.services.transaction import TransactionService


class TransferService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._txn_svc = TransactionService(session)
        self._entity_repo: BaseRepository[Entity] = BaseRepository(session, Entity)
        self._account_repo = AccountRepository(session)
        self._txn_repo = TransactionRepository(session)

    def _resolve_entity(self, entity_id: UUID, role: str) -> None:
        if not self._entity_repo.exists(entity_id):
            raise TransferEntityNotFoundError(f"{role} entity '{entity_id}' not found")

    def _resolve_account(self, entity_id: UUID, code: str, role: str) -> None:
        account = self._account_repo.get_by_entity_and_code(entity_id, code)
        if account is None:
            raise TransferAccountNotFoundError(
                f"Account '{code}' not found for {role} entity '{entity_id}'"
            )

    def transfer(self, payload: TransferCreate, idempotency_key: str) -> tuple[Transaction, Transaction]:
        send_key = f"transfer:send:{idempotency_key}"
        recv_key = f"transfer:recv:{idempotency_key}"

        existing_send = self._txn_repo.get_by_idempotency_key(send_key)
        existing_recv = self._txn_repo.get_by_idempotency_key(recv_key)
        if existing_send and existing_recv:
            return existing_send, existing_recv

        self._resolve_entity(payload.sender_entity_id, "sender")
        self._resolve_entity(payload.receiver_entity_id, "receiver")
        self._resolve_account(payload.sender_entity_id, ACC_TRANSFER, "sender")
        self._resolve_account(payload.sender_entity_id, ACC_RECEIVABLES, "sender")
        self._resolve_account(payload.receiver_entity_id, ACC_TRANSFER, "receiver")
        self._resolve_account(payload.receiver_entity_id, ACC_RECEIVABLES, "receiver")

        sender_txn = self._txn_svc.post(
            payload.sender_entity_id,
            TransactionCreate(
                transaction_type=TransactionType.transfer,
                effective_date=payload.effective_date,
                description=payload.description,
                custom_data={
                    **(payload.custom_data or {}),
                    "counterpart_entity_id": str(payload.receiver_entity_id),
                },
                entries=[
                    TransactionEntryCreate(
                        account_code=ACC_TRANSFER,
                        entry_type=EntryType.debit,
                        amount=payload.amount,
                        currency=payload.currency,
                    ),
                    TransactionEntryCreate(
                        account_code=ACC_RECEIVABLES,
                        entry_type=EntryType.credit,
                        amount=payload.amount,
                        currency=payload.currency,
                    ),
                ],
            ),
            send_key,
        )

        receiver_txn = self._txn_svc.post(
            payload.receiver_entity_id,
            TransactionCreate(
                transaction_type=TransactionType.transfer,
                effective_date=payload.effective_date,
                description=payload.description,
                custom_data={
                    **(payload.custom_data or {}),
                    "counterpart_entity_id": str(payload.sender_entity_id),
                    "counterpart_transaction_id": str(sender_txn.id),
                },
                entries=[
                    TransactionEntryCreate(
                        account_code=ACC_RECEIVABLES,
                        entry_type=EntryType.debit,
                        amount=payload.amount,
                        currency=payload.currency,
                    ),
                    TransactionEntryCreate(
                        account_code=ACC_TRANSFER,
                        entry_type=EntryType.credit,
                        amount=payload.amount,
                        currency=payload.currency,
                    ),
                ],
            ),
            recv_key,
        )

        sender_txn.custom_data = {
            **(sender_txn.custom_data or {}),
            "counterpart_transaction_id": str(receiver_txn.id),
        }

        return sender_txn, receiver_txn
