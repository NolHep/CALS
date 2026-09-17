import json
import pathlib

import pytest

from cals.cache import Cache

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def cache(tmp_path):
    c = Cache(str(tmp_path / "cache.sqlite3"), ttl_seconds=3600)
    yield c
    c.close()


@pytest.fixture
def recap_payload():
    return json.loads((FIXTURES / "recap_search.json").read_text())
