# worker-comfyui

> [ComfyUI](https://github.com/comfyanonymous/ComfyUI) as a serverless API on [RunPod](https://www.runpod.io/)

<p align="center">
  <img src="assets/worker_sitting_in_comfy_chair.jpg" title="Worker sitting in comfy chair" />
</p>

[![RunPod](https://api.runpod.io/badge/runpod-workers/worker-comfyui)](https://www.runpod.io/console/hub/runpod-workers/worker-comfyui)

---

This project runs curated ComfyUI image generation workflows as a serverless API endpoint on the RunPod platform. Submit simple `t2i` or `i2i` requests and receive generated images as base64 strings or S3 URLs.

## Table of Contents

- [Quickstart](#quickstart)
- [Available Docker Images](#available-docker-images)
- [API Specification](#api-specification)
- [Usage](#usage)
- [Customizing Workflow Templates](#customizing-workflow-templates)
- [Further Documentation](#further-documentation)

---

## Quickstart

1.  🐳 Choose one of the [available Docker images](#available-docker-images) for your serverless endpoint (e.g., `runpod/worker-comfyui:<version>-sd3`).
2.  📄 Follow the [Deployment Guide](docs/deployment.md) to set up your RunPod template and endpoint.
3.  ⚙️ Optionally configure the worker (e.g., for S3 upload) using environment variables - see the full [Configuration Guide](docs/configuration.md).
4.  🧪 Send either a text-to-image (`t2i`) or image-to-image (`i2i`) request.
5.  🚀 Follow the [Usage](#usage) steps below to interact with your deployed endpoint.

## Available Docker Images

These images are available on Docker Hub under `runpod/worker-comfyui`:

- **`runpod/worker-comfyui:<version>-base`**: Clean ComfyUI install with no models.
- **`runpod/worker-comfyui:<version>-flux1-schnell`**: Includes checkpoint, text encoders, and VAE for [FLUX.1 schnell](https://huggingface.co/black-forest-labs/FLUX.1-schnell).
- **`runpod/worker-comfyui:<version>-flux1-dev`**: Includes checkpoint, text encoders, and VAE for [FLUX.1 dev](https://huggingface.co/black-forest-labs/FLUX.1-dev).
- **`runpod/worker-comfyui:<version>-flux2-dev`**: Legacy image that included the old Flux2 Dev templates.
- **`runpod/worker-comfyui:<version>-sdxl`**: Includes checkpoint and VAEs for [Stable Diffusion XL](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0).
- **`runpod/worker-comfyui:<version>-sd3`**: Includes checkpoint for [Stable Diffusion 3 medium](https://huggingface.co/stabilityai/stable-diffusion-3-medium).

Replace `<version>` with the current release tag, check the [releases page](https://github.com/runpod-workers/worker-comfyui/releases) for the latest version.

## API Specification

The worker exposes standard RunPod serverless endpoints (`/run`, `/runsync`, `/health`). By default, images are returned as base64 strings. You can configure the worker to upload images to an S3 bucket instead by setting specific environment variables (see [Configuration Guide](docs/configuration.md)).

Use the `/runsync` endpoint for synchronous requests that wait for the job to complete and return the result directly. Use the `/run` endpoint for asynchronous requests that return immediately with a job ID; you'll need to poll the `/status` endpoint separately to get the result.

### Input

```json
{
  "input": {
    "mode": "t2i",
    "prompt": "a ball on the table",
    "aspect_ratio": "1:1",
    "count": 1,
    "options": {
      "steps": 20,
      "cfg": 4,
      "seed": 123456,
      "sampler_name": "euler"
    }
  }
}
```

The following tables describe the fields within the `input` object:

| Field Path                | Type    | Required | Description                                                                                                                   |
| ------------------------- | ------- | -------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `input`                   | Object  | Yes      | Top-level object containing request data.                                                                                     |
| `input.mode`              | String  | Yes      | Generation mode. Supported values are `t2i` and `i2i`.                                                                        |
| `input.prompt`            | String  | Yes      | Positive prompt injected into the built-in workflow template.                                                                 |
| `input.negative_prompt`   | String  | No       | Negative prompt, used only when the selected workflow has a negative prompt node.                                              |
| `input.aspect_ratio`      | String  | No       | Preset size for `t2i`, or explicit resize for `i2i`. Supported values: `1:1`, `16:9`, `9:16`, `4:3`, `3:4`, `3:2`, `2:3`.    |
| `input.width`             | Integer | No       | Explicit output width. Must be paired with `input.height`. Overrides `aspect_ratio`.                                           |
| `input.height`            | Integer | No       | Explicit output height. Must be paired with `input.width`. Overrides `aspect_ratio`.                                          |
| `input.count`             | Integer | No       | Batch size. Defaults to `1`.                                                                                                  |
| `input.image`             | String  | Reserved | Single-image `i2i` is currently disabled until a replacement workflow is added.                                               |
| `input.image_name`        | String  | No       | Filename used when uploading `input.image` to ComfyUI. Defaults to `input_image.png`.                                         |
| `input.images`            | Array   | No       | Image upload array for `i2i`. Send 2-5 images to use the multi-reference workflow. Single-image i2i is currently disabled.   |
| `input.options`           | Object  | No       | Optional sampler fields: `steps`, `seed`, `cfg`, `denoise`, and `sampler_name`.                                                |
| `input.comfy_org_api_key` | String  | No       | Optional per-request Comfy.org API key for API Nodes. Overrides the `COMFY_ORG_API_KEY` environment variable if both are set. |

#### `input.images` Object

Each object within the `input.images` array must contain:

| Field Name | Type   | Required | Description                                                                                                                       |
| ---------- | ------ | -------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `name`     | String | Yes      | Filename used to reference the image in the workflow (e.g., via a "Load Image" node). Must be unique within the array.            |
| `image`    | String | Yes      | Base64 encoded string of the image. A data URI prefix (e.g., `data:image/png;base64,`) is optional and will be handled correctly. |

> [!NOTE]
>
> **Size Limits:** RunPod endpoints have request size limits (e.g., 10MB for `/run`, 20MB for `/runsync`). Large base64 input images can exceed these limits. See [RunPod Docs](https://docs.runpod.io/docs/serverless-endpoint-urls).

### Output

> [!WARNING]
>
> **Breaking Change in Output Format (5.0.0+)**
>
> Versions `< 5.0.0` returned the primary image data (S3 URL or base64 string) directly within an `output.message` field.
> Starting with `5.0.0`, the output format has changed significantly, see below

```json
{
  "id": "sync-uuid-string",
  "status": "COMPLETED",
  "output": {
    "images": [
      {
        "filename": "ComfyUI_00001_.png",
        "type": "base64",
        "data": "iVBORw0KGgoAAAANSUhEUg..."
      }
    ]
  },
  "delayTime": 123,
  "executionTime": 4567
}
```

| Field Path      | Type             | Required | Description                                                                                                 |
| --------------- | ---------------- | -------- | ----------------------------------------------------------------------------------------------------------- |
| `output`        | Object           | Yes      | Top-level object containing the results of the job execution.                                               |
| `output.images` | Array of Objects | No       | Present if the workflow generated images. Contains a list of objects, each representing one output image.   |
| `output.errors` | Array of Strings | No       | Present if non-fatal errors or warnings occurred during processing (e.g., S3 upload failure, missing data). |

#### `output.images`

Each object in the `output.images` array has the following structure:

| Field Name | Type   | Description                                                                                     |
| ---------- | ------ | ----------------------------------------------------------------------------------------------- |
| `filename` | String | The original filename assigned by ComfyUI during generation.                                    |
| `type`     | String | Indicates the format of the data. Either `"base64"` or `"s3_url"` (if S3 upload is configured). |
| `data`     | String | Contains either the base64 encoded image string or the S3 URL for the uploaded image file.      |

> [!NOTE]
> The `output.images` field provides a list of all generated images (excluding temporary ones).
>
> - If S3 upload is **not** configured (default), `type` will be `"base64"` and `data` will contain the base64 encoded image string.
> - If S3 upload **is** configured, `type` will be `"s3_url"` and `data` will contain the S3 URL. See the [Configuration Guide](docs/configuration.md#example-s3-response) for an S3 example response.
> - Clients interacting with the API need to handle this list-based structure under `output.images`.

## Usage

To interact with your deployed RunPod endpoint:

1.  **Get API Key:** Generate a key in RunPod [User Settings](https://www.runpod.io/console/serverless/user/settings) (`API Keys` section).
2.  **Get Endpoint ID:** Find your endpoint ID on the [Serverless Endpoints](https://www.runpod.io/console/serverless/user/endpoints) page or on the `Overview` page of your endpoint.

### Generate Image (Sync Example)

Send a generation request to the `/runsync` endpoint (waits for completion). Replace `<api_key>` and `<endpoint_id>`. The `-d` value should contain the [JSON input described above](#input).

```bash
curl -X POST \
  -H "Authorization: Bearer <api_key>" \
  -H "Content-Type: application/json" \
  -d '{"input":{"mode":"t2i","prompt":"a ball on the table","aspect_ratio":"1:1"}}' \
  https://api.runpod.ai/v2/<endpoint_id>/runsync
```

For image-to-image, send `mode: "i2i"` with an `images` array containing 2-5 images. Single-image i2i is currently disabled until a replacement workflow is added:

```json
{
  "input": {
    "mode": "i2i",
    "prompt": "make a photo of the monkey riding the bicycle on a city street",
    "images": [
      {
        "name": "monkey.png",
        "image": "data:image/png;base64,iVBOR..."
      },
      {
        "name": "bicycle.png",
        "image": "data:image/png;base64,iVBOR..."
      }
    ]
  }
}
```

You can also use the `/run` endpoint for asynchronous jobs and then poll the `/status` to see when the job is done. Or you [add a `webhook` into your request](https://docs.runpod.io/serverless/endpoints/send-requests#webhook-notifications) to be notified when the job is done.

Refer to [`docs/api-testing.md`](./docs/api-testing.md) and [`sample_payloads/`](./sample_payloads/) for ready-to-send RunPod test payloads.
For third-party integration, use the [Image API Contract](docs/image-api-contract.md)
as the request/response reference.

## Customizing Workflow Templates

The public API no longer accepts a raw `input.workflow` payload. The worker loads built-in templates from [`workflows/`](./workflows/) and injects request fields into those templates.

To replace a built-in template:

1.  Open ComfyUI in your browser.
2.  In the top navigation, select `Workflow > Export (API)`
3.  Save the exported JSON over `workflows/flux2_klein_t2i.json` or `workflows/flux2_klein_multi_i2i.json`.
4.  Rebuild the Docker image.

## SSH Access

To enable SSH access to the worker, set the `PUBLIC_KEY` environment variable to your SSH public key. The worker will start an SSH server automatically. Make sure to expose **port 22** in your RunPod template so you can connect.

## Further Documentation

- **[Deployment Guide](docs/deployment.md):** Detailed steps for deploying on RunPod.
- **[API Testing Guide](docs/api-testing.md):** RunPod curl commands and sample payloads for `t2i` and `i2i`.
- **[Image API Contract](docs/image-api-contract.md):** Payload and response reference for third-party image generation integrations.
- **[Configuration Guide](docs/configuration.md):** Full list of environment variables (including S3 setup).
- **[Customization Guide](docs/customization.md):** Adding custom models and nodes (Network Volumes, Docker builds).
- **[Development Guide](docs/development.md):** Setting up a local environment for development & testing
- **[CI/CD Guide](docs/ci-cd.md):** Information about the automated Docker build and publish workflows.
- **[Acknowledgments](docs/acknowledgments.md):** Credits and thanks
