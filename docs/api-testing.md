# API Testing Guide

> Wan2.2 video quick curls are documented below. Set `RUNPOD_API_KEY` and `ENDPOINT_ID`, then use `/runsync` for blocking tests or `/run` plus `/status/<job_id>` for async tests.

This worker exposes RunPod serverless endpoints and accepts a simplified custom input payload. Clients do not send raw ComfyUI workflow JSON anymore.

## Wan2.2 Video Curl Examples

Set these variables before running the examples:

```bash
export RUNPOD_API_KEY="<runpod_api_key>"
export ENDPOINT_ID="<endpoint_id>"
```

Wan2.2 video outputs are uploaded to S3-compatible storage and returned as `s3_url` artifacts. Configure `BUCKET_ENDPOINT_URL`, `BUCKET_ACCESS_KEY_ID`, and `BUCKET_SECRET_ACCESS_KEY` before running production video tests.

Text-to-video sync test:

```bash
curl -X POST \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"input":{"mode":"t2v","prompt":"A cinematic shot of a red aircraft crossing a stormy sky","resolution":"720p","aspect_ratio":"16:9","duration":"auto","generate_audio":false}}' \
  "https://api.runpod.ai/v2/${ENDPOINT_ID}/runsync"
```

Text-to-video async test:

```bash
curl -X POST \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"input":{"mode":"t2v","prompt":"A slow dolly shot through a neon city street at night","resolution":"480p","aspect_ratio":"16:9","duration":4,"options":{"fps":16,"steps":20}}}' \
  "https://api.runpod.ai/v2/${ENDPOINT_ID}/run"
```

For a first RTX 4090 benchmark, start with the same 480p payload above and set these endpoint environment variables:

```text
COMFY_LOG_LEVEL=INFO
COMFY_EXTRA_ARGS=--cuda-malloc --use-split-cross-attention
```

If the worker still takes several minutes, check the ComfyUI logs for model load/offload messages. The default Wan2.2 14B workflow uses separate high-noise and low-noise expert models, so a 24 GB GPU may still move model weights through system RAM. Test `--highvram` separately only after confirming it does not produce CUDA out-of-memory errors:

```text
COMFY_EXTRA_ARGS=--cuda-malloc --use-split-cross-attention --highvram
```

Check async job status:

```bash
curl -X GET \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  "https://api.runpod.ai/v2/${ENDPOINT_ID}/status/<job_id>"
```

Image-to-video sync test with inline frame:

```bash
curl -X POST \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"input":{"mode":"i2v","prompt":"Preserve the subject identity, add subtle cinematic camera motion","start_frame":"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...","resolution":"720p","aspect_ratio":"16:9","duration":4,"options":{"fps":24,"steps":30,"motion_strength":0.45,"strength":0.6}}}' \
  "https://api.runpod.ai/v2/${ENDPOINT_ID}/runsync"
```

Reference-to-video sync test with first and last frame URLs:

```bash
curl -X POST \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"input":{"mode":"r2v","prompt":"Animate smoothly from the first frame to the last frame with natural motion","image_urls":["https://example.com/start.png","https://example.com/end.png"],"resolution":"720p","aspect_ratio":"16:9","duration":5,"options":{"fps":24,"steps":30,"motion_strength":0.5}}}' \
  "https://api.runpod.ai/v2/${ENDPOINT_ID}/runsync"
```

Expected successful video output shape:

```json
{
  "id": "sync-...",
  "status": "COMPLETED",
  "output": {
    "videos": [
      {
        "filename": "WanVideo_00001.mp4",
        "type": "s3_url",
        "data": "https://..."
      }
    ],
    "meta": {
      "mode": "t2v",
      "model": "wan2.2-14b",
      "fps": 24,
      "duration_sec": 5,
      "warnings": []
    }
  }
}
```

## Legacy Flux2 Image Curl Examples

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
