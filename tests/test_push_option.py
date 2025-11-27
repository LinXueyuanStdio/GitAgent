import importlib.util
from pathlib import Path


GCLI_PATH = Path(__file__).resolve().parents[1] / "gcli.py"
SPEC = importlib.util.spec_from_file_location("local_gcli", GCLI_PATH)
gcli = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(gcli)


def test_resolve_auto_push_uses_config_when_cli_option_is_omitted():
    assert gcli.resolve_auto_push({"auto_push": True}, None) is True
    assert gcli.resolve_auto_push({"auto_push": False}, None) is False


def test_resolve_auto_push_cli_option_overrides_config():
    assert gcli.resolve_auto_push({"auto_push": True}, False) is False
    assert gcli.resolve_auto_push({"auto_push": False}, True) is True
