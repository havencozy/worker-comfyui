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
    ├── checkpoints/      # Stable Diffusion checkpoints (.safetensors, .ckpt)
    ├── loras/            # LoRA files (.safetensors, .pt)
    ├── vae/              # VAE models (.safetensors, .pt)
    ├── clip/             # CLIP models (.safetensors, .pt)
    ├── text_encoders/    # Text encoder models used by newer Flux workflows
    ├── clip_vision/      # CLIP Vision models
    ├── diffusion_models/ # Diffusion model files used by UNETLoader
    ├── controlnet/       # ControlNet models (.safetensors, .pt)
    ├── embeddings/       # Textual inversion embeddings (.safetensors, .pt)
    ├── upscale_models/   # Upscaling models (.safetensors, .pt)
    ├── unet/             # UNet models
    └── configs/          # Model configs (.yaml, .json)
```

> **Note**
>
> Only create the subdirectories you actually need; empty or missing folders are fine.

## Preparing Flux2 Models on a Network Volume

For the custom `t2i` and `i2i` endpoints, prefer storing Flux2 model files on a RunPod Network Volume instead of baking them into the Docker image. This keeps image builds smaller and avoids long `exporting layers` times.

When preparing the volume from a RunPod Pod, the network volume is usually mounted at `/workspace`. The same volume is mounted at `/runpod-volume` inside serverless workers.

Run this once from a Pod attached to the same network volume:

```bash
# 1. Move to the network volume root inside the setup Pod
cd /workspace

# 2. Create the model directories expected by the worker
mkdir -p models/text_encoders models/diffusion_models models/vae models/loras

# 3. Download Text Encoder (Mistral, used by standard Flux2 t2i/i2i)
wget --show-progress \
  -O models/text_encoders/mistral_3_small_flux2_bf16.safetensors \
  https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/text_encoders/mistral_3_small_flux2_bf16.safetensors

# 4. Download core Diffusion model (Flux2 Dev FP8)
wget --show-progress \
  -O models/diffusion_models/flux2_dev_fp8mixed.safetensors \
  https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/diffusion_models/flux2_dev_fp8mixed.safetensors

# 5. Download VAE
wget --show-progress \
  -O models/vae/flux2-vae.safetensors \
  https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/vae/flux2-vae.safetensors

# 6. Download Turbo LoRA used by the Flux2 image setup
wget --show-progress \
  -O models/loras/Flux_2-Turbo-LoRA_comfyui.safetensors \
  https://huggingface.co/ByteZSzn/Flux.2-Turbo-ComfyUI/resolve/main/Flux_2-Turbo-LoRA_comfyui.safetensors
```

Then configure the serverless endpoint with:

```text
COMFY_ROOT=/runpod-volume
```

This makes runtime model preflight checks look for files under `/runpod-volume/models/...`, matching the files created under `/workspace/models/...` in the setup Pod.

If the Hugging Face download requires authentication, set `HUGGINGFACE_ACCESS_TOKEN` or `HF_TOKEN` on the worker. The runtime downloader uses those variables when it needs to fetch missing files.

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


