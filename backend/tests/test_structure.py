import importlib

import pytest

SPEC_MODULES = [
    "upload", "profiling", "cleaning", "context", "modelling", "dax",
    "insights", "planner", "stitch_prompt", "design_import", "pbip_builder", "validator",
]


@pytest.mark.parametrize("name", SPEC_MODULES)
def test_spec_module_importable(name):
    importlib.import_module(f"core.{name}")
