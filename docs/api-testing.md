# API Testing Guide

This worker exposes RunPod serverless endpoints and accepts a simplified custom input payload. Clients do not send raw ComfyUI workflow JSON anymore.

For third-party integrations that need the exact payload and response contract,
see the [Image API Contract](image-api-contract.md).

## Endpoints

Replace `<endpoint_id>` and `<runpod_api_key>` before running the examples.

Synchronous generation:

```bash
curl -X POST \
  -H "Authorization: Bearer <runpod_api_key>" \
  -H "Content-Type: application/json" \
  --data @sample_payloads/t2i-minimal.json \
  https://api.runpod.ai/v2/<endpoint_id>/runsync
```

Asynchronous generation:

```bash
curl -X POST \
  -H "Authorization: Bearer <runpod_api_key>" \
  -H "Content-Type: application/json" \
  --data @sample_payloads/t2i-minimal.json \
  https://api.runpod.ai/v2/<endpoint_id>/run
```

Check async job status:

```bash
curl -X GET \
  -H "Authorization: Bearer <runpod_api_key>" \
  https://api.runpod.ai/v2/<endpoint_id>/status/<job_id>
```

## Payload Contract

All requests must wrap the custom payload under `input`.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `input.mode` | string | yes | Supported values: `t2i`, `i2i`. |
| `input.prompt` | string | yes | Positive prompt injected into the selected workflow template. |
| `input.negative_prompt` | string | no | Used only when the workflow template contains a negative prompt node. |
| `input.model` | string | no | Optional model preset. Current built-in preset with runtime asset manifest: `flux2-dev`. |
| `input.aspect_ratio` | string | no | Supported presets: `1:1`, `16:9`, `9:16`, `4:3`, `3:4`, `3:2`, `2:3`. |
| `input.width` | integer | no | Explicit output width. Must be sent with `height`. Overrides `aspect_ratio`. |
| `input.height` | integer | no | Explicit output height. Must be sent with `width`. Overrides `aspect_ratio`. |
| `input.count` | integer | no | Batch size. Defaults to `1`; must be `>= 1`. |
| `input.image` | string | i2i only | Base64 image. Data URI prefix is supported. |
| `input.image_name` | string | no | Filename used when uploading `input.image`. Defaults to `input_image.png`. |
| `input.images` | array | no | Legacy-compatible i2i upload format. First image is wired into the Load Image node. |
| `input.options` | object | no | Optional sampler overrides: `steps`, `seed`, `cfg`, `denoise`, `sampler_name`, `model`. |
| `input.comfy_org_api_key` | string | no | Per-request Comfy.org API key. Overrides `COMFY_ORG_API_KEY`. |

Notes:

- `t2i` defaults to `1024x1024` when no size is provided.
- `i2i` preserves the source image size by default. Send `aspect_ratio` or `width`/`height` only when you want to resize.
- `input.model` and `input.options.model` are equivalent; `options.model` wins if both are present.
- Do not send `input.workflow`; this API builds the workflow internally from `workflows/flux2_t2i.json` or `workflows/flux2_i2i.json`.

## Sample Payloads

Minimal text-to-image:

```bash
curl -X POST \
  -H "Authorization: Bearer <runpod_api_key>" \
  -H "Content-Type: application/json" \
  --data @sample_payloads/t2i-minimal.json \
  https://api.runpod.ai/v2/<endpoint_id>/runsync
```

Advanced text-to-image:

```bash
curl -X POST \
  -H "Authorization: Bearer <runpod_api_key>" \
  -H "Content-Type: application/json" \
  --data @sample_payloads/t2i-advanced.json \
  https://api.runpod.ai/v2/<endpoint_id>/runsync
```

Image-to-image:

```bash
curl -X POST \
  -H "Authorization: Bearer <runpod_api_key>" \
  -H "Content-Type: application/json" \
  --data @sample_payloads/i2i-minimal.json \
  https://api.runpod.ai/v2/<endpoint_id>/runsync
```

Available sample files:

| File | Purpose |
| --- | --- |
| `sample_payloads/t2i-minimal.json` | Smallest valid text-to-image request. |
| `sample_payloads/t2i-advanced.json` | Text-to-image with model preset, size preset, seed, steps, CFG, sampler. |
| `sample_payloads/t2i-explicit-size.json` | Text-to-image with explicit `width` and `height`. |
| `sample_payloads/i2i-minimal.json` | Smallest valid image-to-image request with inline base64 image. |
| `sample_payloads/i2i-advanced.json` | Image-to-image with model preset and sampler options. |
| `sample_payloads/i2i-legacy-images-array.json` | Image-to-image using the legacy `images` array shape. |

## Expected Response

RunPod wraps the worker output:

```json
{
  "id": "sync-...",
  "status": "COMPLETED",
  "output": {
    "images": [
      {
        "filename": "Flux2_00001_.png",
        "type": "base64",
        "data": "iVBORw0KGgo..."
      }
    ]
  }
}
```

If S3 output is configured, `type` is `s3_url` and `data` is the uploaded image URL.

## Common Errors

`Missing or invalid 'mode'. Supported values: 't2i', 'i2i'`

The request body is missing `input.mode`, or the endpoint is receiving only the inner object without the RunPod `input` wrapper.

`Missing 'prompt' parameter`

Send `input.prompt`.

`Missing 'image' (or 'images') parameter for i2i mode`

For `mode: "i2i"`, send either `input.image` or `input.images`.

`Unsupported model '<name>'`

Use `flux2-dev`, or configure `FLUX_MODEL_PRESETS_JSON` and `FLUX_MODEL_ASSETS_JSON` for another model.

`Failed downloading ...`

The selected model is missing locally and runtime download failed. Check `HUGGINGFACE_ACCESS_TOKEN` or bake the model into the image/network volume.
