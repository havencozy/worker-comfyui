# worker-comfyui

> [ComfyUI](https://github.com/comfyanonymous/ComfyUI) as a serverless API on [RunPod](https://www.runpod.io/)

<p align="center">
  <img src="assets/worker_sitting_in_comfy_chair.jpg" title="Worker sitting in comfy chair" />
</p>

[![RunPod](https://api.runpod.io/badge/runpod-workers/worker-comfyui)](https://www.runpod.io/console/hub/runpod-workers/worker-comfyui)

---

This project runs curated ComfyUI Wan2.2 video generation workflows as a serverless API endpoint on the RunPod platform. Submit `t2v`, `i2v`, or `r2v` requests and receive generated video artifacts as S3 URLs.

## Table of Contents

- [Quickstart](#quickstart)
- [Available Docker Images](#available-docker-images)
- [API Specification](#api-specification)
- [Usage](#usage)
- [Customizing Workflow Templates](#customizing-workflow-templates)
- [Further Documentation](#further-documentation)

---

## Quickstart

1.  🐳 Choose one of the [available Docker images](#available-docker-images) for your serverless endpoint (e.g., `runpod/worker-comfyui:<version>-wan2.2-14b`).
2.  📄 Follow the [Deployment Guide](docs/deployment.md) to set up your RunPod template and endpoint.
3.  ⚙️ Optionally configure the worker (e.g., for S3 upload) using environment variables - see the full [Configuration Guide](docs/configuration.md).
4.  🧪 Send a text-to-video (`t2v`), image-to-video (`i2v`), or first-last-frame (`r2v`) request.
5.  🚀 Follow the [Usage](#usage) steps below to interact with your deployed endpoint.

## Available Docker Images

These images are available on Docker Hub under `runpod/worker-comfyui`:

- **`runpod/worker-comfyui:<version>-base`**: Clean ComfyUI install with no models.
- **`runpod/worker-comfyui:<version>-wan2.2-volume`**: Wan2.2 video worker with no baked models, intended for Network Volume model mounts.
- **`runpod/worker-comfyui:<version>-wan2.2-14b`**: Includes Wan2.2 14B T2V/I2V diffusion models, text encoder, and VAE for video generation.

Replace `<version>` with the current release tag, check the [releases page](https://github.com/runpod-workers/worker-comfyui/releases) for the latest version.

## API Specification

The worker exposes standard RunPod serverless endpoints (`/run`, `/runsync`, `/health`). Generated videos are uploaded to S3-compatible storage and returned as `s3_url` artifacts. Configure S3 before deploying this video worker (see [Configuration Guide](docs/configuration.md)).

Use the `/runsync` endpoint for synchronous requests that wait for the job to complete and return the result directly. Use the `/run` endpoint for asynchronous requests that return immediately with a job ID; you'll need to poll the `/status` endpoint separately to get the result.

### Input

```json
{
  "input": {
    "mode": "t2v",
    "prompt": "A cinematic shot of a red aircraft crossing a stormy sky",
    "negative_prompt": "low quality, blur",
    "resolution": "720p",
    "duration": "auto",
    "aspect_ratio": "16:9",
    "seed": 12345,
    "generate_audio": false,
    "options": {
      "fps": 24,
      "steps": 30,
      "guidance_scale": 7.5,
      "motion_strength": 0.5,
      "strength": 0.6
    }
  }
}
```

Supported modes:

- `t2v` / `wan22-t2v`: text-to-video using Wan2.2 14B T2V.
- `i2v` / `wan22-i2v`: image-to-video using Wan2.2 14B I2V. Requires `start_frame` as a data URI or base64 string.
- `r2v` / `wan22-flf2v`: first-last-frame video using Wan2.2 14B FLF2V. Requires `start_frame` and `end_frame`, or `image_urls[0]` and `image_urls[1]`.

Wan2.2 T2V/I2V/FLF2V outputs silent videos. `generate_audio=true` is accepted but returns `AUDIO_NOT_SUPPORTED_BY_WORKFLOW` in `meta.warnings`.

The following fields are supported within the `input` object:

| Field Path | Type | Required | Description |
| ---------- | ---- | -------- | ----------- |
| `input.mode` | String | Yes | Supported values: `t2v`, `i2v`, `r2v`; aliases: `wan22-t2v`, `wan22-i2v`, `wan22-flf2v`. |
| `input.prompt` | String | Yes | Positive prompt injected into the selected Wan2.2 workflow. |
| `input.negative_prompt` | String | No | Negative prompt, defaults to an empty string. |
| `input.resolution` | String | No | `480p`, `720p`, or `1080p`. Defaults to `720p`. |
| `input.duration` | String or Integer | No | `auto` or integer seconds from `4` to `15`. `auto` means 5 seconds. Ignored when `input.options.length` is set. |
| `input.aspect_ratio` | String | No | `auto`, `21:9`, `16:9`, `4:3`, `1:1`, `3:4`, or `9:16`. `auto` maps to `16:9`. |
| `input.seed` | Integer | No | Sampler seed from `0` to `2147483647`. |
| `input.generate_audio` | Boolean | No | Accepted for API compatibility, but Wan2.2 T2V/I2V/FLF2V does not generate audio. |
| `input.start_frame` | String | `i2v`, `r2v` alternative | Data URI or base64 frame. Use `image_urls` for remote HTTP(S) frames. |
| `input.end_frame` | String | `r2v` alternative | Data URI or base64 frame. Use `image_urls` for remote HTTP(S) frames. |
| `input.start_frame_name` | String | No | Filename used when uploading `start_frame`. Defaults to `start_frame.png`. |
| `input.end_frame_name` | String | No | Filename used when uploading `end_frame`. Defaults to `end_frame.png`. |
| `input.image_urls` | Array | `r2v` alternative | First two image URLs are used as start/end frames when `start_frame` and `end_frame` are not supplied. |
| `input.video_urls` | Array | No | Not consumed in this Wan2.2 FLF2V deployment. `@VideoN` prompt references are rejected. |
| `input.audio_urls` | Array | No | Not consumed in this Wan2.2 FLF2V deployment. `@AudioN` prompt references are rejected. |
| `input.comfy_org_api_key` / `input.api_key_comfy_org` | String | No | Optional per-request Comfy.org API key override for workflows that use ComfyUI API Nodes. |
| `input.options.fps` | Integer | No | `8..30`, defaults to `24`. |
| `input.options.steps` | Integer | No | `10..80`, defaults to `30`. Wan2.2 dual samplers split this into high-noise and low-noise ranges. |
| `input.options.guidance_scale` | Number | No | `1..20`, defaults to `7.5`; maps to sampler `cfg`. |
| `input.options.motion_strength` | Number | No | `0..1`, defaults to `0.5`. |
| `input.options.strength` | Number | No | `0..1`, defaults to `0.6`. |
| `input.options.length` | Integer | No | Direct frame count override, `1..450`. When set, `duration_sec = length / fps`. |

### Output

```json
{
  "id": "sync-uuid-string",
  "status": "COMPLETED",
  "output": {
    "videos": [
      {
        "filename": "out.mp4",
        "type": "s3_url",
        "data": "https://..."
      }
    ],
    "meta": {
      "mode": "t2v",
      "model": "wan2.2-14b",
      "seed": 12345,
      "fps": 24,
      "duration_sec": 5,
      "num_frames": 120,
      "width": 1280,
      "height": 720,
      "warnings": []
    }
  },
  "delayTime": 123,
  "executionTime": 4567
}
```

| Field Path | Type | Description |
| ---------- | ---- | ----------- |
| `output.videos` | Array | Generated video artifacts. |
| `output.videos[].filename` | String | Filename assigned by ComfyUI. |
| `output.videos[].type` | String | Always `s3_url` for production video deployment. |
| `output.videos[].data` | String | S3 URL for the uploaded video. |
| `output.meta` | Object | Normalized request and workflow metadata. |
| `output.errors` | Array | Present if non-fatal warnings or artifact handling errors occurred. |

## Usage

To interact with your deployed RunPod endpoint:

1.  **Get API Key:** Generate a key in RunPod [User Settings](https://www.runpod.io/console/serverless/user/settings) (`API Keys` section).
2.  **Get Endpoint ID:** Find your endpoint ID on the [Serverless Endpoints](https://www.runpod.io/console/serverless/user/endpoints) page or on the `Overview` page of your endpoint.

### Generate Video (Sync Example)

Send a generation request to the `/runsync` endpoint (waits for completion). Replace `<api_key>` and `<endpoint_id>`. The `-d` value should contain the [JSON input described above](#input).

```bash
curl -X POST \
  -H "Authorization: Bearer <api_key>" \
  -H "Content-Type: application/json" \
  -d '{"input":{"mode":"t2v","prompt":"A cinematic shot of a red aircraft crossing a stormy sky","resolution":"720p","aspect_ratio":"16:9"}}' \
  https://api.runpod.ai/v2/<endpoint_id>/runsync
```

For image-to-video, send `mode: "i2v"` and include `start_frame`:

```json
{
  "input": {
    "mode": "i2v",
    "prompt": "preserve identity, cinematic motion",
    "start_frame": "data:image/png;base64,iVBOR..."
  }
}
```

For reference-to-video, send `mode: "r2v"` with start and end frames, or provide two `image_urls`.

You can also use the `/run` endpoint for asynchronous jobs and then poll the `/status` to see when the job is done. Or you [add a `webhook` into your request](https://docs.runpod.io/serverless/endpoints/send-requests#webhook-notifications) to be notified when the job is done.

Refer to [`test_input.json`](./test_input.json) for a ready-to-send RunPod test payload.

## Customizing Workflow Templates

The public API no longer accepts a raw `input.workflow` payload. The worker loads built-in templates from [`workflows/`](./workflows/) and injects request fields into those templates.

To replace a built-in template:

1.  Open ComfyUI in your browser.
2.  In the top navigation, select `Workflow > Export (API)`
3.  Save the exported JSON over `workflows/wan2_2_14b_t2v.json`, `workflows/wan2_2_14b_i2v.json`, or `workflows/wan2_2_14b_flf2v.json`.
4.  Rebuild the Docker image.

## SSH Access

To enable SSH access to the worker, set the `PUBLIC_KEY` environment variable to your SSH public key. The worker will start an SSH server automatically. Make sure to expose **port 22** in your RunPod template so you can connect.

## Further Documentation

- **[Deployment Guide](docs/deployment.md):** Detailed steps for deploying on RunPod.
- **[API Testing Guide](docs/api-testing.md):** RunPod curl commands for Wan2.2 video generation.
- **[Configuration Guide](docs/configuration.md):** Full list of environment variables (including S3 setup).
- **[Network Volumes & Model Paths](docs/network-volumes.md):** RunPod Network Volume layout and `wget` commands for preloading Wan2.2 models when building with `MODEL_TYPE=none`.
- **[Customization Guide](docs/customization.md):** Adding custom models and nodes (Network Volumes, Docker builds).
- **[Development Guide](docs/development.md):** Setting up a local environment for development & testing
- **[CI/CD Guide](docs/ci-cd.md):** Information about the automated Docker build and publish workflows.
- **[Acknowledgments](docs/acknowledgments.md):** Credits and thanks
