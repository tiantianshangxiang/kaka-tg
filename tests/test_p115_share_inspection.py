import importlib.util
import sys
import types
import unittest
from pathlib import Path


logger = types.SimpleNamespace(info=lambda *_a, **_k: None, warn=lambda *_a, **_k: None)
sys.modules.setdefault("app", types.ModuleType("app"))
log_module = sys.modules.setdefault("app.log", types.ModuleType("app.log"))
log_module.logger = logger
PATH = Path(__file__).resolve().parents[1] / "plugins.v2" / "tgsearch115" / "p115_transfer.py"
spec = importlib.util.spec_from_file_location("tgsearch115_p115_transfer", PATH)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class ShareInspectionTest(unittest.TestCase):
    def test_inspection_reads_names_without_share_receive(self):
        client = module.P115Transfer("UID=x; CID=y; SEID=z")
        calls = []
        client._api_get = lambda path, params: calls.append((path, params)) or {
            "state": True, "data": {"list": [{"n": "Silo.S02.2024.1080p.CHINESE"}]}
        }
        client._api_post = lambda *_args, **_kwargs: self.fail("inspection must not post")

        ok, _message, names = client.inspect_share("https://115.com/s/demo?password=abcd")

        self.assertTrue(ok)
        self.assertEqual(["Silo.S02.2024.1080p.CHINESE"], names)
        self.assertEqual("/share/snap", calls[0][0])

    def test_inspection_requires_receive_code(self):
        client = module.P115Transfer("UID=x; CID=y; SEID=z")
        ok, _message, names = client.inspect_share("https://115.com/s/demo")
        self.assertFalse(ok)
        self.assertEqual([], names)


if __name__ == "__main__":
    unittest.main()
