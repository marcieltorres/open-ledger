from unittest import TestCase
from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from src.exceptions.entity import DuplicateEntityError, EntityNotFoundError
from src.model.entity import Entity
from src.model.schemas.entities import EntityCreate, EntityUpdate
from src.services.entity import EntityService


def _make_entity(**kwargs) -> Entity:
    entity = Entity(
        external_id=kwargs.get("external_id", "ext-001"),
        name=kwargs.get("name", "ACME"),
        enabled=kwargs.get("enabled", True),
        parent_entity_id=kwargs.get("parent_entity_id", None),
        custom_data=kwargs.get("custom_data", None),
    )
    entity.id = kwargs.get("id", uuid4())
    return entity


class EntityServiceCreateTest(TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.service = EntityService(self.session)
        self.service._repo = MagicMock()

    def test_create_success(self):
        entity = _make_entity()
        payload = EntityCreate(external_id="ext-001", name="ACME")
        self.service._repo.exists.return_value = False
        self.service._repo.save.return_value = entity
        result = self.service.create(payload)
        self.service._repo.save.assert_called_once()
        self.assertEqual(result, entity)

    def test_create_with_valid_parent(self):
        entity = _make_entity()
        parent_id = uuid4()
        payload = EntityCreate(external_id="child", parent_entity_id=parent_id)
        self.service._repo.exists.return_value = True
        self.service._repo.save.return_value = entity
        self.service.create(payload)
        self.service._repo.exists.assert_called_once_with(parent_id)

    def test_create_with_invalid_parent_raises(self):
        payload = EntityCreate(external_id="child", parent_entity_id=uuid4())
        self.service._repo.exists.return_value = False
        with self.assertRaises(EntityNotFoundError):
            self.service.create(payload)

    def test_create_duplicate_raises(self):
        payload = EntityCreate(external_id="ext-001")
        self.service._repo.exists.return_value = False
        self.service._repo.save.side_effect = IntegrityError(None, None, None)
        with self.assertRaises(DuplicateEntityError):
            self.service.create(payload)
        self.session.rollback.assert_called_once()


class EntityServiceGetByIdTest(TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.service = EntityService(self.session)
        self.service._repo = MagicMock()

    def test_get_by_id_returns_entity(self):
        entity = _make_entity()
        self.service._repo.get_by_id.return_value = entity
        self.assertEqual(self.service.get_by_id(entity.id), entity)

    def test_get_by_id_not_found_raises(self):
        self.service._repo.get_by_id.return_value = None
        with self.assertRaises(EntityNotFoundError):
            self.service.get_by_id(uuid4())


class EntityServiceListTest(TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.service = EntityService(self.session)
        self.service._repo = MagicMock()

    def test_list_returns_all(self):
        self.service._repo.get_all.return_value = [_make_entity(), _make_entity()]
        self.assertEqual(len(self.service.list()), 2)
        self.service._repo.get_all.assert_called_once_with(skip=0, limit=100)

    def test_list_with_pagination(self):
        self.service._repo.get_all.return_value = [_make_entity()]
        self.service.list(skip=10, limit=5)
        self.service._repo.get_all.assert_called_once_with(skip=10, limit=5)


class EntityServiceUpdateTest(TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.service = EntityService(self.session)
        self.service._repo = MagicMock()

    def test_update_name_and_metadata(self):
        entity = _make_entity()
        self.service._repo.get_by_id.return_value = entity
        self.service._repo.save.return_value = entity
        self.service.update(entity.id, EntityUpdate(name="New", custom_data={"k": "v"}))
        self.assertEqual(entity.name, "New")
        self.assertEqual(entity.custom_data, {"k": "v"})
        self.service._repo.save.assert_called_once_with(entity)

    def test_update_only_name(self):
        entity = _make_entity()
        self.service._repo.get_by_id.return_value = entity
        self.service._repo.save.return_value = entity
        self.service.update(entity.id, EntityUpdate(name="New"))
        self.assertEqual(entity.name, "New")
        self.service._repo.save.assert_called_once_with(entity)

    def test_update_only_metadata(self):
        entity = _make_entity()
        self.service._repo.get_by_id.return_value = entity
        self.service._repo.save.return_value = entity
        self.service.update(entity.id, EntityUpdate(custom_data={"k": "v"}))
        self.assertEqual(entity.custom_data, {"k": "v"})
        self.service._repo.save.assert_called_once_with(entity)

    def test_update_no_fields_saves_unchanged(self):
        entity = _make_entity()
        self.service._repo.get_by_id.return_value = entity
        self.service._repo.save.return_value = entity
        result = self.service.update(entity.id, EntityUpdate())
        self.service._repo.save.assert_called_once_with(entity)
        self.assertEqual(result, entity)

    def test_update_not_found_raises(self):
        self.service._repo.get_by_id.return_value = None
        with self.assertRaises(EntityNotFoundError):
            self.service.update(uuid4(), EntityUpdate(name="New"))
