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
        self.assertIn('/comfyui/.venv/bin/python -c "import torch', self.dockerfile)

    def test_installs_comfyui_boot_dependencies(self):
        dockerfile = self.dockerfile.lower()
        self.assertIn("sqlalchemy", dockerfile)
        self.assertIn("alembic", dockerfile)
        self.assertIn("comfy_aimdo.control", dockerfile)
        self.assertIn("blake3", dockerfile)
        self.assertIn("from app.assets.seeder import asset_seeder", dockerfile)

    def test_wan22_model_type_downloads_required_models(self):
        self.assertIn('MODEL_TYPE" = "wan2.2-14b"', self.dockerfile)
        self.assertIn(
            "wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors",
            self.dockerfile,
        )
        self.assertIn(
            "wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors",
            self.dockerfile,
        )
        self.assertIn(
            "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
            self.dockerfile,
        )
        self.assertIn(
            "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
            self.dockerfile,
        )
        self.assertIn("umt5_xxl_fp8_e4m3fn_scaled.safetensors", self.dockerfile)
        self.assertIn("wan_2.1_vae.safetensors", self.dockerfile)


if __name__ == "__main__":
    unittest.main()
