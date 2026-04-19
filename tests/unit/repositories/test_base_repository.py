from unittest import TestCase
from unittest.mock import MagicMock
from uuid import uuid4

from src.model.entity import Entity
from src.repositories.base import BaseRepository


class BaseRepositoryTest(TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.repo = BaseRepository(self.session, Entity)

    def _mock_first(self, value):
        self.session.query.return_value.filter.return_value.first.return_value = value

    def test_get_by_id_returns_entity(self):
        entity = Entity(external_id="ext-001", enabled=True)
        self._mock_first(entity)
        self.assertEqual(self.repo.get_by_id(uuid4()), entity)

    def test_get_by_id_returns_none_when_not_found(self):
        self._mock_first(None)
        self.assertIsNone(self.repo.get_by_id(uuid4()))

    def test_get_all_returns_list(self):
        entities = [Entity(), Entity()]
        self.session.query.return_value.offset.return_value.limit.return_value.all.return_value = entities
        self.assertEqual(len(self.repo.get_all()), 2)

    def test_save_adds_instance_and_flushes(self):
        entity = Entity(external_id="ext-001", enabled=True)
        result = self.repo.save(entity)
        self.session.add.assert_called_once_with(entity)
        self.session.flush.assert_called_once()
        self.assertIs(result, entity)

    def test_delete_deletes_entity(self):
        entity = Entity()
        entity.id = uuid4()
        self._mock_first(entity)
        self.assertTrue(self.repo.delete(entity.id))
        self.session.delete.assert_called_once_with(entity)
        self.session.flush.assert_called_once()

    def test_delete_returns_false_when_not_found(self):
        self._mock_first(None)
        self.assertFalse(self.repo.delete(uuid4()))

    def test_exists_returns_true(self):
        self._mock_first(Entity())
        self.assertTrue(self.repo.exists(uuid4()))

    def test_exists_returns_false(self):
        self._mock_first(None)
        self.assertFalse(self.repo.exists(uuid4()))

    def test_list_by_field_returns_matching_entities(self):
        entities = [Entity(external_id="ext-001"), Entity(external_id="ext-001")]
        self.session.query.return_value.filter.return_value.all.return_value = entities
        result = self.repo.list_by_field("external_id", "ext-001")
        self.assertEqual(len(result), 2)

    def test_get_by_field_returns_first_match(self):
        entity = Entity(external_id="ext-001")
        self.session.query.return_value.filter.return_value.all.return_value = [entity]
        result = self.repo.get_by_field("external_id", "ext-001")
        self.assertEqual(result, entity)

    def test_get_by_field_returns_none_when_not_found(self):
        self.session.query.return_value.filter.return_value.all.return_value = []
        self.assertIsNone(self.repo.get_by_field("external_id", "missing"))
