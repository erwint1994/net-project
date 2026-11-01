"""Smoke test: Blender builds a net and renders a quick preview. Skipped when Blender isn't found or NET_SKIP_BLENDER=1.

  python -m unittest tests.test_blender_smoke -v
"""
import os
import shutil
import unittest

from studio import config, runner


@unittest.skipIf(os.environ.get("NET_SKIP_BLENDER") == "1", "NET_SKIP_BLENDER=1")
class BlenderSmoke(unittest.TestCase):
    def test_quick_build_of_every_state(self):
        if runner.find_blender()[0] is None:
            self.skipTest("Blender not found")
        cfg, _ = config.resolve(config.deep_merge(config.load_preset("net_42_two_piece"), {"id": "net_smoke_test"}))
        lines = []
        try:
            for state in ("deployed", "scooping"):
                code, out = runner.run(cfg, quick=True, state=state, on_line=lines.append)
                self.assertEqual(code, 0, "\n".join(lines[-30:]))
                self.assertTrue((out / "previews" / f"quick_{state}.png").exists())
            self.assertTrue(any("LOD0" in line and "tris" in line for line in lines))
        finally:
            shutil.rmtree(runner.OUTPUT / "net_smoke_test", ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
