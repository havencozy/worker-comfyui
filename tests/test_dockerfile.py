import unittest
from pathlib import Path


class TestDockerfileRunpodBuildDefaults(unittest.TestCase):
    def setUp(self):
        self.dockerfile = Path("Dockerfile").read_text()
        self.docker_bake = Path("docker-bake.hcl").read_text()
        self.github_workflows = "\n".join(
            path.read_text()
            for path in Path(".github/workflows").glob("*.yml")
        )

    def test_plain_docker_build_uses_cuda_130_comfy_defaults(self):
        self.assertIn("ARG COMFYUI_VERSION=v0.21.1", self.dockerfile)
        self.assertIn('default = "v0.21.1"', self.docker_bake)
        self.assertIn(
            "ARG BASE_IMAGE=nvidia/cuda:13.0.0-cudnn-runtime-ubuntu24.04",
            self.dockerfile,
        )
        self.assertIn("ARG CUDA_VERSION_FOR_COMFY=", self.dockerfile)
        self.assertIn("ARG ENABLE_PYTORCH_UPGRADE=true", self.dockerfile)
        self.assertIn(
            "ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cu130",
            self.dockerfile,
        )

    def test_build_fails_if_torch_is_not_importable(self):
        self.assertIn('/comfyui/.venv/bin/python -c "import torch', self.dockerfile)

    def test_comfy_install_uses_posix_sh_compatible_syntax(self):
        self.assertNotIn("set +o pipefail", self.dockerfile)
        self.assertIn(
            'RUN if [ -n "${CUDA_VERSION_FOR_COMFY}" ]; then',
            self.dockerfile,
        )

    def test_installs_handler_dependencies_from_requirements_before_app_code(self):
        self.assertIn("COPY requirements.txt ./", self.dockerfile)
        self.assertIn("RUN uv pip install -r requirements.txt", self.dockerfile)
        self.assertLess(
            self.dockerfile.index("RUN uv pip install -r requirements.txt"),
            self.dockerfile.index("ADD src/start.sh"),
        )

    def test_bake_has_wan22_volume_target_without_model_download_stage(self):
        self.assertIn('target "wan2.2-volume"', self.docker_bake)
        self.assertIn('target = "base"', self.docker_bake)
        self.assertIn('MODEL_TYPE = "none"', self.docker_bake)
        self.assertIn('-wan2.2-volume', self.docker_bake)

    def test_video_branch_does_not_define_legacy_non_video_build_targets(self):
        combined = (
            f"{self.dockerfile}\n{self.docker_bake}\n{self.github_workflows}"
        ).lower()
        disallowed_terms = [
            "sd" + "xl",
            "sd" + "3",
            "z-" + "image-turbo",
            "fl" + "ux1-schnell",
            "fl" + "ux1-dev",
            "fl" + "ux1-dev-fp8",
            "base-cuda" + "12",
        ]
        for term in disallowed_terms:
            self.assertNotIn(term, combined)

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
