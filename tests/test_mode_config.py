import unittest
from unittest.mock import AsyncMock, patch

import mode_config as module


class ModeConfigTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        module._resolved = None

    def tearDown(self) -> None:
        module._resolved = None

    async def test_resolve_mode_true_sets_local(self) -> None:
        with patch.dict(module.os.environ, {"MOCK_MODE": "true"}, clear=True):
            result = await module.resolve_mode()

        self.assertEqual(result, "local")
        self.assertTrue(module.is_local())

    async def test_resolve_mode_false_sets_azure(self) -> None:
        with patch.dict(module.os.environ, {"MOCK_MODE": "false"}, clear=True):
            result = await module.resolve_mode()

        self.assertEqual(result, "azure")
        self.assertFalse(module.is_local())

    async def test_resolve_mode_dynamic_uses_probe(self) -> None:
        with patch.dict(module.os.environ, {"MOCK_MODE": "dynamic"}, clear=True):
            with patch("mode_config._probe_azure", AsyncMock(return_value="local")):
                result = await module.resolve_mode()

        self.assertEqual(result, "local")
        self.assertTrue(module.is_local())

    def test_is_local_raises_before_resolution(self) -> None:
        with self.assertRaises(RuntimeError):
            module.is_local()


if __name__ == "__main__":
    unittest.main()
