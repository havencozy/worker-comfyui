# Build argument for base image selection
ARG BASE_IMAGE=nvidia/cuda:13.0.0-cudnn-runtime-ubuntu24.04

# Stage 1: Base image with common dependencies
FROM ${BASE_IMAGE} AS base

# Build arguments for this stage with sensible defaults for standalone builds
ARG COMFYUI_VERSION=v0.21.1
ARG CUDA_VERSION_FOR_COMFY=
ARG ENABLE_PYTORCH_UPGRADE=true
ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cu130

# Prevents prompts from packages asking for user input during installation
ENV DEBIAN_FRONTEND=noninteractive
# Prefer binary wheels over source distributions for faster pip installations
ENV PIP_PREFER_BINARY=1
# Ensures output from python is printed immediately to the terminal without buffering
ENV PYTHONUNBUFFERED=1
# Speed up some cmake builds
ENV CMAKE_BUILD_PARALLEL_LEVEL=8

# Install Python, git and other necessary tools
RUN apt-get update && apt-get install -y \
    python3.12 \
    python3.12-venv \
    git \
    wget \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    ffmpeg \
    openssh-server \
    && ln -sf /usr/bin/python3.12 /usr/bin/python \
    && ln -sf /usr/bin/pip3 /usr/bin/pip

# Clean up to reduce image size
RUN apt-get autoremove -y && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Install uv (latest) using official installer and create isolated venv
RUN wget -qO- https://astral.sh/uv/install.sh | sh \
    && ln -s /root/.local/bin/uv /usr/local/bin/uv \
    && ln -s /root/.local/bin/uvx /usr/local/bin/uvx \
    && uv venv /opt/venv

# Use the virtual environment for all subsequent commands
ENV PATH="/opt/venv/bin:${PATH}"

# Install comfy-cli + dependencies needed by it to install ComfyUI
RUN uv pip install comfy-cli pip setuptools wheel

# Install ComfyUI
RUN if [ -n "${CUDA_VERSION_FOR_COMFY}" ]; then \
        /usr/bin/yes | comfy --workspace /comfyui install --version "${COMFYUI_VERSION}" --cuda-version "${CUDA_VERSION_FOR_COMFY}" --nvidia; \
    else \
        /usr/bin/yes | comfy --workspace /comfyui install --version "${COMFYUI_VERSION}" --nvidia; \
    fi

# Upgrade PyTorch if needed (for newer CUDA versions)
RUN if [ "$ENABLE_PYTORCH_UPGRADE" = "true" ]; then \
      /comfyui/.venv/bin/python -m pip install --force-reinstall torch torchvision torchaudio --index-url ${PYTORCH_INDEX_URL}; \
    fi

# Ensure plain Docker builds, including RunPod GitHub builds that do not use
# docker-bake.hcl, fail during build instead of producing workers without torch.
RUN if ! /comfyui/.venv/bin/python -c "import torch; assert torch.version.cuda, 'PyTorch CUDA wheel is not installed'; print(f'torch={torch.__version__}, cuda={torch.version.cuda}')"; then \
      /comfyui/.venv/bin/python -m pip install --force-reinstall torch torchvision torchaudio --index-url ${PYTORCH_INDEX_URL}; \
      /comfyui/.venv/bin/python -c "import torch; assert torch.version.cuda, 'PyTorch CUDA wheel is not installed'; print(f'torch={torch.__version__}, cuda={torch.version.cuda}')"; \
    fi

# Change working directory to ComfyUI
WORKDIR /comfyui

# Support for the network volume
ADD src/extra_model_paths.yaml ./

# Smoke test the import chain that ComfyUI executes before binding port 8188.
RUN /comfyui/.venv/bin/python -c "import blake3, comfy_aimdo.control, sqlalchemy, alembic; from app.assets.seeder import asset_seeder; print('ComfyUI boot imports OK')"

# Go back to the root
WORKDIR /

# Install Python runtime dependencies for the handler before application code so
# code-only edits can reuse dependency layers.
COPY requirements.txt ./
RUN uv pip install -r requirements.txt

# Add application code and scripts
ADD src/start.sh src/network_volume.py handler.py test_input.json ./
ADD workflows ./workflows
RUN chmod +x /start.sh

# Add script to install custom nodes
COPY scripts/comfy-node-install.sh /usr/local/bin/comfy-node-install
RUN chmod +x /usr/local/bin/comfy-node-install

# Prevent pip from asking for confirmation during uninstall steps in custom nodes
ENV PIP_NO_INPUT=1

# Copy helper script to switch Manager network mode at container start
COPY scripts/comfy-manager-set-mode.sh /usr/local/bin/comfy-manager-set-mode
RUN chmod +x /usr/local/bin/comfy-manager-set-mode

# Set the default command to run when starting the container
CMD ["/start.sh"]

# Stage 2: Download models
FROM base AS downloader

# NOTE:
# - Default to no model download during image build to avoid RunPod build timeout.
# - Recommended approach: keep models on Network Volume / persistent storage and
#   download at runtime (once), instead of baking large weights into image layers.
# - Set MODEL_TYPE explicitly if you intentionally want to bake models into image.
ARG MODEL_TYPE=none

# Change working directory to ComfyUI
WORKDIR /comfyui

# Create necessary directories upfront
RUN mkdir -p models/checkpoints models/vae models/unet models/clip models/text_encoders models/diffusion_models models/model_patches models/loras models/audio_encoders models/upscale_models

# Download Wan2.2 video models only when explicitly requested.
RUN if [ "$MODEL_TYPE" = "wan2.2-14b" ]; then \
      wget -q -O models/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors && \
      wget -q -O models/diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors && \
      wget -q -O models/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors && \
      wget -q -O models/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors && \
      wget -q -O models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors && \
      wget -q -O models/vae/wan_2.1_vae.safetensors https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors; \
    fi

# Stage 3: Final image
FROM base AS final

# Copy models from stage 2 to the final image
COPY --from=downloader /comfyui/models /comfyui/models
