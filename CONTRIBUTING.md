# Contributing [![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](CODE_OF_CONDUCT.md)

Welcome, please read with careful and patience our manifest and coding style.

# Be pythonic!

```
Beautiful is better than ugly.
Explicit is better than implicit.
Simple is better than complex.
Complex is better than complicated.
Flat is better than nested.
Sparse is better than dense.
Readability counts.
Special cases aren't special enough to break the rules.
Although practicality beats purity.
Errors should never pass silently.
Unless explicitly silenced.
In the face of ambiguity, refuse the temptation to guess.
There should be one-- and preferably only one --obvious way to do it.
Although that way may not be obvious at first unless you're Dutch.
Now is better than never.
Although never is often better than *right* now.
If the implementation is hard to explain, it's a bad idea.
If the implementation is easy to explain, it may be a good idea.
Namespaces are one honking great idea -- let's do more of those!
```
[The zen of python - PEP20](https://www.python.org/dev/peps/pep-0020/)

# Manifest

- First of all: **Be pythonic** :)
- [DRY](http://deviq.com/don-t-repeat-yourself/) - Don't repeat yourself.
- [KISS](https://deviq.com/keep-it-simple/) - Keep it simple stupid.

# Coding Style

We are using [Ruff](https://github.com/astral-sh/ruff) to manage the coding style [rules](https://beta.ruff.rs/docs/rules/).

Rule | Description
--- | ---
E,W | [pycode style](https://pypi.org/project/pycodestyle/)
F | [pyflakes](https://pypi.org/project/pyflakes/)
I | [isort](https://pypi.org/project/isort/)
N | [pep8-naming](https://pypi.org/project/pep8-naming/)
S | [flake8-bandit](https://pypi.org/project/flake8-bandit/)

# Exception Conventions

Domain exceptions live in `src/exceptions/`, with one file per domain:

- `src/exceptions/entity.py` — exceptions related to the entity domain
- `src/exceptions/account.py` — exceptions related to the account domain

Rules:
- Each exception class extends `Exception` with a `pass` body
- `src/exceptions/__init__.py` re-exports all exceptions for convenience
- Source files must use direct domain-specific imports (e.g. `from src.exceptions.entity import EntityNotFoundError`), not the package root
- Routes catch domain exceptions and convert them to `HTTPException` with the appropriate HTTP status code

Example:

```python
# src/exceptions/entity.py
class EntityNotFoundError(Exception):
    pass

# src/routes/entities.py
from src.exceptions.entity import EntityNotFoundError

try:
    entity = service.get_by_id(entity_id)
except EntityNotFoundError as e:
    raise HTTPException(status_code=404, detail=str(e))
```

# Integration Tests with Database

We use [Testcontainers](https://testcontainers.com/) for database integration tests. A PostgreSQL container starts automatically when tests run.

**Writing a database test:**

```python
from unittest import TestCase
from sqlalchemy import text

class MyDatabaseTest(TestCase):
    db_session = None  # Injected automatically

    def test_example(self):
        result = self.db_session.execute(text("SELECT 1"))
        self.assertEqual(result.scalar(), 1)
```

- Place tests in `tests/it/`
- Use `self.db_session` for database operations
- Use `self.db_engine` when needed
- Each test gets an isolated session with automatic rollback
