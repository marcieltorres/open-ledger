from uuid import UUID

from sqlalchemy.orm import Session

from src.exceptions.account import AccountNotFoundError, InvalidTemplateError
from src.exceptions.entity import EntityNotFoundError
from src.model.chart_of_accounts import ChartOfAccounts
from src.model.entity import Entity
from src.model.schemas.accounts import AccountProvision, AccountUpdate
from src.repositories.account import AccountRepository
from src.repositories.base import BaseRepository
from src.services.templates import get_template


class AccountService:
    def __init__(self, session: Session) -> None:
        self._repo = AccountRepository(session)
        self._entity_repo: BaseRepository[Entity] = BaseRepository(session, Entity)

    def provision(self, entity_id: UUID, payload: AccountProvision) -> list[ChartOfAccounts]:
        if not self._entity_repo.exists(entity_id):
            raise EntityNotFoundError(f"Entity '{entity_id}' not found")

        if payload.template is not None:
            account_list = get_template(payload.template)
        elif payload.accounts is not None:
            account_list = payload.accounts
        else:
            raise InvalidTemplateError("Either 'template' or 'accounts' must be provided")

        results = []
        for account_create in account_list:
            existing = self._repo.get_by_entity_and_code(entity_id, account_create.code)
            if existing is not None:
                results.append(existing)
                continue
            account = ChartOfAccounts(
                entity_id=entity_id,
                code=account_create.code,
                name=account_create.name,
                account_type=account_create.account_type,
                category=account_create.category,
                currency=account_create.currency,
                custom_data=account_create.custom_data,
            )
            results.append(self._repo.save(account))
        return results

    def list_by_entity(self, entity_id: UUID) -> list[ChartOfAccounts]:
        if not self._entity_repo.exists(entity_id):
            raise EntityNotFoundError(f"Entity '{entity_id}' not found")
        return self._repo.get_by_entity(entity_id)

    def get_by_id(self, entity_id: UUID, account_id: UUID) -> ChartOfAccounts:
        if not self._entity_repo.exists(entity_id):
            raise EntityNotFoundError(f"Entity '{entity_id}' not found")
        account = self._repo.get_by_id(account_id)
        if account is None or account.entity_id != entity_id:
            raise AccountNotFoundError(f"Account '{account_id}' not found for entity '{entity_id}'")
        return account

    def update(self, entity_id: UUID, account_id: UUID, payload: AccountUpdate) -> ChartOfAccounts:
        account = self.get_by_id(entity_id, account_id)
        for field, value in payload.model_dump().items():
            if value is not None:
                setattr(account, field, value)
        return self._repo.save(account)
