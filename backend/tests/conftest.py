import os

os.environ.setdefault("AUTH", "off")  # tests run without Firebase; test_auth flips it per test

import json
from pathlib import Path

import pytest

from app.growth import crop_from_dict

SEED = Path(__file__).resolve().parents[2] / "data" / "seed"


@pytest.fixture(scope="session")
def pakcoy():
    return crop_from_dict(json.loads((SEED / "crops.json").read_text())[0])
