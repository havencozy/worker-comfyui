# Network Volumes & Model Paths

This document explains how to use RunPod **Network Volumes** with `worker-comfyui`, how model paths are resolved inside the container, and how to debug cases where models are not detected.

> **Scope**
>
> These instructions apply to **serverless endpoints** using this worker. Pods mount network volumes at `/workspace` by default, while serverless workers see them at `/runpod-volume`.

## Directory Mapping

For **serverless endpoints**:

- Network volume root is mounted at: `/runpod-volume`
- ComfyUI models are expected under: `/runpod-volume/models/...`

For **Pods**:

- Network volume root is mounted at: `/workspace`
- Equivalent ComfyUI model path: `/workspace/models/...`

If you use the S3-compatible API, the same paths map as:

- Serverless: `/runpod-volume/my-folder/file.txt`
- Pod: `/workspace/my-folder/file.txt`
- S3 API: `s3://<NETWORK_VOLUME_ID>/my-folder/file.txt`

## Expected Directory Structure

Models must be placed in the following structure on your network volume:

```text
/runpod-volume/
└── models/
    ├── checkpoints/      # Checkpoint models when used by custom video workflows
    ├── loras/            # LoRA files (.safetensors, .pt)
    ├── vae/              # VAE models (.safetensors, .pt)
    ├── clip/             # CLIP models (.safetensors, .pt)
    ├── text_encoders/    # Text encoder models used by newer workflows
    ├── clip_vision/      # CLIP Vision models
    ├── diffusion_models/ # Diffusion model files used by UNETLoader
    ├── controlnet/       # ControlNet models (.safetensors, .pt)
    ├── embeddings/       # Textual inversion embeddings (.safetensors, .pt)
    ├── upscale_models/   # Upscaling models (.safetensors, .pt)
    ├── latent_upscale_models/ # Latent upscalers used by LTX workflows
    ├── unet/             # UNet models
    └── configs/          # Model configs (.yaml, .json)
```

> **Note**
>
> Only create the subdirectories you actually need; empty or missing folders are fine.

## Preparing Wan2.2 14B Video Models on a Network Volume

For the Wan2.2 video worker, prefer building the Docker image with `MODEL_TYPE=none` and storing model files on a RunPod Network Volume. This keeps builds small and avoids repeatedly downloading large model files during image builds.

Build the worker image without baked models:

```bash
docker build --platform linux/amd64 \
  --build-arg MODEL_TYPE=none \
  -t worker-comfyui:wan2.2-video .
```

Then prepare the network volume once from a RunPod Pod attached to the same volume. In setup Pods, the network volume is usually mounted at `/workspace`; the same volume is mounted at `/runpod-volume` inside serverless workers.

Run this once from the setup Pod:

```bash
# 1. Move to the network volume root inside the setup Pod
cd /workspace

# 2. Create the model directories expected by the worker
mkdir -p models/diffusion_models models/text_encoders models/vae

# 3. Download Wan2.2 T2V high-noise diffusion model
wget --show-progress \
  -O models/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors \
  https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors

# 4. Download Wan2.2 T2V low-noise diffusion model
wget --show-progress \
  -O models/diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors \
  https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors

# 5. Download Wan2.2 I2V high-noise diffusion model
wget --show-progress \
  -O models/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors \
  https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors

# 6. Download Wan2.2 I2V low-noise diffusion model
wget --show-progress \
  -O models/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors \
  https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors

# 7. Download Wan text encoder
wget --show-progress \
  -O models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors \
  https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors

# 8. Download Wan VAE
wget --show-progress \
  -O models/vae/wan_2.1_vae.safetensors \
  https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors
```

Expected serverless worker view after attaching the volume:

```text
/runpod-volume/
└── models/
    ├── diffusion_models/
    │   ├── wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors
    │   ├── wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors
    │   ├── wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors
    │   └── wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors
    ├── text_encoders/
    │   └── umt5_xxl_fp8_e4m3fn_scaled.safetensors
    └── vae/
        └── wan_2.1_vae.safetensors
```

The handler checks these files before each job. If any are missing, the job fails before ComfyUI execution with `MODEL_ASSET_MISSING` and lists the missing filenames.

Default search roots are:

```text
/runpod-volume/models
/comfyui/models
```

You can override the roots with `WAN22_MODEL_ROOTS` using a colon-separated list:

```text
WAN22_MODEL_ROOTS=/runpod-volume/models:/custom/models
```

## Preparing LTX-2.3 Video Models on a Network Volume

For LTX-2.3, use the same network volume layout under `/runpod-volume/models/...`.
The worker payload does not change: use `input.mode=ltx-t2v` or
`input.mode=ltx-i2v`, and make sure the LTX model files are present on the
attached volume before the job starts.

Create these directories on the volume:

```bash
mkdir -p \
  /workspace/models/diffusion_models \
  /workspace/models/loras \
  /workspace/models/text_encoders \
  /workspace/models/vae \
  /workspace/models/latent_upscale_models
```

Download the workflow's required files to these exact paths:

```bash
wget --show-progress \
  -O /workspace/models/diffusion_models/ltx-2.3-22b-distilled-UD-Q4_K_M.gguf \
  https://huggingface.co/unsloth/LTX-2.3-GGUF/resolve/main/distilled/ltx-2.3-22b-distilled-UD-Q4_K_M.gguf

wget --show-progress \
  -O /workspace/models/loras/ltx-2.3-22b-distilled-lora-dynamic_fro09_avg_rank_105_bf16.safetensors \
  https://huggingface.co/Kijai/LTX2.3_comfy/resolve/main/loras/ltx-2.3-22b-distilled-lora-dynamic_fro09_avg_rank_105_bf16.safetensors

wget --show-progress \
  -O /workspace/models/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors \
  https://huggingface.co/Comfy-Org/ltx-2/resolve/main/split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors

wget --show-progress \
  -O /workspace/models/text_encoders/ltx-2.3_text_projection_bf16.safetensors \
  https://huggingface.co/Kijai/LTX2.3_comfy/resolve/main/text_encoders/ltx-2.3_text_projection_bf16.safetensors

wget --show-progress \
  -O /workspace/models/vae/ltx-2.3-22b-dev_audio_vae.safetensors \
  https://huggingface.co/unsloth/LTX-2.3-GGUF/resolve/main/vae/ltx-2.3-22b-dev_audio_vae.safetensors

wget --show-progress \
  -O /workspace/models/vae/ltx-2.3-22b-dev_video_vae.safetensors \
  https://huggingface.co/unsloth/LTX-2.3-GGUF/resolve/main/vae/ltx-2.3-22b-dev_video_vae.safetensors

wget --show-progress \
  -O /workspace/models/latent_upscale_models/ltx-2.3-spatial-upscaler-x2-1.1.safetensors \
  https://huggingface.co/Oveei/LTX-2.3/resolve/main/ltx-2.3-spatial-upscaler-x2-1.1.safetensors
```

Expected serverless worker view after attaching the same volume:

```text
/runpod-volume/
└── models/
    ├── diffusion_models/
    │   └── ltx-2.3-22b-distilled-UD-Q4_K_M.gguf
    ├── loras/
    │   └── ltx-2.3-22b-distilled-lora-dynamic_fro09_avg_rank_105_bf16.safetensors
    ├── text_encoders/
    │   ├── gemma_3_12B_it_fp4_mixed.safetensors
    │   └── ltx-2.3_text_projection_bf16.safetensors
    ├── vae/
    │   ├── ltx-2.3-22b-dev_audio_vae.safetensors
    │   └── ltx-2.3-22b-dev_video_vae.safetensors
    └── latent_upscale_models/
        └── ltx-2.3-spatial-upscaler-x2-1.1.safetensors
```

If any of these files are missing or placed in the wrong subdirectory, ComfyUI
will fail when the LTX workflow starts. Unlike Wan2.2, the worker currently
does not fail fast on missing LTX assets before workflow execution.

## Supported File Extensions

ComfyUI only recognizes files with specific extensions when scanning model directories.

| Model Type     | Supported Extensions                        |
| -------------- | ------------------------------------------- |
| Checkpoints    | `.safetensors`, `.ckpt`, `.pt`, `.pth`, `.bin` |
| LoRAs          | `.safetensors`, `.pt`                       |
| VAE            | `.safetensors`, `.pt`, `.bin`               |
| CLIP           | `.safetensors`, `.pt`, `.bin`               |
| Text Encoders  | `.safetensors`, `.pt`, `.bin`               |
| Diffusion Models | `.safetensors`, `.pt`, `.pth`, `.bin`     |
| ControlNet     | `.safetensors`, `.pt`, `.pth`, `.bin`       |
| Embeddings     | `.safetensors`, `.pt`, `.bin`               |
| Upscale Models | `.safetensors`, `.pt`, `.pth`               |

Files with other extensions (for example `.txt`, `.zip`) are **ignored** by ComfyUI’s model discovery.

## Common Issues

- **Wrong root directory**
  - Models placed directly under `/runpod-volume/checkpoints/...` instead of `/runpod-volume/models/checkpoints/...`.
- **Incorrect extensions**
  - Files named without one of the supported extensions are skipped.
- **Empty directories**
  - No actual model files present in `models/checkpoints` (or other folders).
- **Volume not attached**
  - Endpoint created without selecting a network volume under **Advanced → Select Network Volume**.

If any of the above is true, ComfyUI will silently fail to discover models from the network volume.

## Debugging with `NETWORK_VOLUME_DEBUG`

The worker exposes an opt‑in debug mode controlled via the `NETWORK_VOLUME_DEBUG` environment variable.

### When to Use

Enable this when:

- Models on your network volume are not appearing in ComfyUI
- You suspect the directory structure or file extensions are wrong
- You want to quickly verify what the worker can actually see on `/runpod-volume`

### How to Enable

1. Go to your serverless **Endpoint → Manage → Edit**.
2. Under **Environment Variables**, add:

   - `NETWORK_VOLUME_DEBUG=true`

3. Save and wait for workers to restart (or scale to zero and back up).
4. Send any request to your endpoint (even a minimal one) to trigger the diagnostics.

### Reading the Diagnostics

When enabled, each request prints a detailed report to the worker logs, for example:

```text
======================================================================
NETWORK VOLUME DIAGNOSTICS (NETWORK_VOLUME_DEBUG=true)
======================================================================

[1] Checking extra_model_paths.yaml configuration...
    ✓ FOUND: /comfyui/extra_model_paths.yaml

[2] Checking network volume mount at /runpod-volume...
    ✓ MOUNTED: /runpod-volume

[3] Checking directory structure...
    ✓ FOUND: /runpod-volume/models

[4] Scanning model directories...

    checkpoints/:
      - my-model.safetensors (6.5 GB)

    loras/:
      - style-lora.safetensors (144.2 MB)

[5] Summary
    ✓ Models found on network volume!
======================================================================
```

If there is a problem, the diagnostics will instead highlight it, for example:

- Missing `models/` directory
- No valid model files in any subdirectory
- Files present but ignored due to wrong extensions

### Disabling Debug Mode

Once you have resolved your issue, disable diagnostics to keep logs clean:

- Remove the `NETWORK_VOLUME_DEBUG` environment variable, **or**
- Set `NETWORK_VOLUME_DEBUG=false`

This returns the worker to normal behavior without extra log noise.
