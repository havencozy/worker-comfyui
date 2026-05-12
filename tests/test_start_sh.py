import unittest
from pathlib import Path


class TestStartScriptPythonEnvironments(unittest.TestCase):
    def setUp(self):
        self.start_sh = Path("src/start.sh").read_text()

    def test_comfyui_runs_with_comfy_workspace_venv(self):
        self.assertIn('COMFY_PYTHON="${COMFY_PYTHON:-/comfyui/.venv/bin/python}"', self.start_sh)
        self.assertIn('"$COMFY_PYTHON" -u /comfyui/main.py', self.start_sh)

    def test_handler_runs_with_handler_venv(self):
        self.assertIn('HANDLER_PYTHON="${HANDLER_PYTHON:-/opt/venv/bin/python}"', self.start_sh)
        self.assertIn('"$HANDLER_PYTHON" -u /handler.py', self.start_sh)

    def test_gpu_check_can_be_skipped_for_local_cpu_smoke_test(self):
        self.assertIn('SKIP_GPU_CHECK', self.start_sh)


if __name__ == "__main__":
    unittest.main()
