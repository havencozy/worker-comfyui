import unittest
from pathlib import Path


class TestDockerfileRunpodBuildDefaults(unittest.TestCase):
    def setUp(self):
        self.dockerfile = Path("Dockerfile").read_text()

    def test_plain_docker_build_uses_cuda_126_comfy_defaults(self):
        self.assertIn("ARG CUDA_VERSION_FOR_COMFY=12.6", self.dockerfile)
        self.assertIn(
            "ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cu126",
            self.dockerfile,
        )

    def test_build_fails_if_torch_is_not_importable(self):
        self.assertIn('python -c "import torch', self.dockerfile)

    def test_installs_comfyui_boot_dependencies(self):
        dockerfile = self.dockerfile.lower()
        self.assertIn("sqlalchemy", dockerfile)
        self.assertIn("alembic", dockerfile)


if __name__ == "__main__":
    unittest.main()
