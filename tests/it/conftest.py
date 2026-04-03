import pytest


@pytest.fixture(autouse=True)
def inject_fixtures(request, db_engine, db_session):
    """Inject fixtures into TestCase instances."""
    if request.instance is not None:
        request.instance.db_engine = db_engine
        request.instance.db_session = db_session
