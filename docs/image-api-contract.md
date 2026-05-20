# Image API Contract

This document is for third-party clients that call the deployed RunPod endpoint
to generate images. It only describes HTTP payloads and responses.

## Base URL

```text
https://api.runpod.ai/v2/<ENDPOINT_ID>
```

## Authentication

Send the RunPod API key in the `Authorization` header:

```http
Authorization: Bearer <RUNPOD_API_KEY>
Content-Type: application/json
```

Keep the RunPod API key on your backend. Do not expose it in browser or mobile
client code.

## Endpoints

| Endpoint | Method | Use case |
| --- | --- | --- |
| `/runsync` | `POST` | Blocking request. Returns final output when the job completes or times out. |
| `/run` | `POST` | Async request. Returns a job ID immediately. |
| `/status/<JOB_ID>` | `GET` | Poll async job status and final output. |

## Supported Modes

| `input.mode` | Type | Required fields |
| --- | --- | --- |
| `t2i` | Text-to-image | `prompt` |
| `i2i` | Image-to-image | `prompt`, plus `image` or `images` |

The API does not accept raw ComfyUI workflow JSON. The worker selects a built-in
workflow from `input.mode` and injects supported request fields into that
workflow.

## Request Body

All generation parameters must be wrapped under `input`.

```json
{
  "input": {
    "mode": "t2i",
    "model": "flux2-dev",
    "prompt": "a premium product photo of matte black wireless headphones on brushed steel",
    "negative_prompt": "blurry, low quality, distorted, text, watermark",
    "aspect_ratio": "3:2",
    "count": 1,
    "options": {
      "steps": 20,
      "cfg": 4,
      "seed": 649422536169327,
      "sampler_name": "euler"
    }
  }
}
```

## Request Fields

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `input.mode` | string | yes | none | `t2i` or `i2i`. |
| `input.prompt` | string | yes | none | Positive prompt. Must be non-empty. |
| `input.negative_prompt` | string | no | workflow default | Negative prompt. Used only when the workflow contains a negative prompt node. |
| `input.model` | string | no | workflow default | Model preset. Built-in preset with runtime asset manifest: `flux2-dev`. |
| `input.aspect_ratio` | string | no | `1:1` for `t2i`; source size for `i2i` | Preset size. Supported: `1:1`, `16:9`, `9:16`, `4:3`, `3:4`, `3:2`, `2:3`. |
| `input.width` | integer | no | mode default | Explicit output width. Send with `height`. Overrides `aspect_ratio` only when both are present. |
| `input.height` | integer | no | mode default | Explicit output height. Send with `width`. Overrides `aspect_ratio` only when both are present. |
| `input.count` | integer | no | `1` | Batch size. Must be `>= 1`. |
| `input.image` | string | `i2i` option | none | Base64 input image. Data URI prefix is supported. |
| `input.image_name` | string | no | `input_image.png` | Filename used when uploading `input.image` to ComfyUI. |
| `input.images` | object[] | `i2i` option | none | Image upload format. One image uses the standard i2i workflow; 2-5 images use the multi-reference workflow. |
| `input.comfy_org_api_key` | string | no | env default | Per-request Comfy.org API key override for workflows using ComfyUI API Nodes. |
| `input.options` | object | no | `{}` | Sampler/model overrides. See [Options](#options). |

For `i2i`, send either:

- `input.image` with optional `input.image_name`, or
- `input.images`, where each item has `name` and `image`.

`input.images` accepts at most 5 images.

## Options

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `input.options.model` | string | no | Same as `input.model`. If both are sent, `options.model` wins. |
| `input.options.steps` | integer | no | Injected into workflow nodes with a `steps` input. |
| `input.options.seed` | integer | no | Injected into workflow `seed` or `noise_seed` inputs. |
| `input.options.cfg` | number | no | Injected into workflow `cfg` inputs and Flux guidance nodes. |
| `input.options.denoise` | number | no | Injected into workflow nodes with a `denoise` input. |
| `input.options.sampler_name` | string | no | Injected into workflow nodes with a `sampler_name` input. |

## Aspect Ratio Presets

| `aspect_ratio` | Width x Height |
| --- | --- |
| `1:1` | `1024 x 1024` |
| `16:9` | `1344 x 768` |
| `9:16` | `768 x 1344` |
| `4:3` | `1152 x 896` |
| `3:4` | `896 x 1152` |
| `3:2` | `1216 x 832` |
| `2:3` | `832 x 1216` |

`t2i` defaults to `1024 x 1024` when no size is provided. `i2i` preserves the
source image size by default unless `aspect_ratio` or explicit `width` and
`height` are sent.

## Text-To-Image Payloads

Minimal:

```json
{
  "input": {
    "mode": "t2i",
    "prompt": "a cinematic portrait photo, natural skin texture, soft light"
  }
}
```

With model preset and sampler options:

```json
{
  "input": {
    "mode": "t2i",
    "model": "flux2-dev",
    "prompt": "a premium product photo of a matte black wireless headphone on brushed steel, softbox lighting, crisp details",
    "negative_prompt": "blurry, low quality, distorted, text, watermark",
    "aspect_ratio": "3:2",
    "count": 1,
    "options": {
      "steps": 20,
      "cfg": 4,
      "seed": 649422536169327,
      "sampler_name": "euler"
    }
  }
}
```

With explicit size:

```json
{
  "input": {
    "mode": "t2i",
    "prompt": "an editorial fashion photo in a clean concrete studio, high detail, natural pose",
    "width": 1024,
    "height": 1024,
    "count": 1,
    "options": {
      "steps": 16,
      "cfg": 3.5,
      "seed": 123456789,
      "sampler_name": "euler"
    }
  }
}
```

## Image-To-Image Payloads

Inline base64 image:

```json
{
  "input": {
    "mode": "i2i",
    "model": "flux2-dev",
    "prompt": "preserve composition, convert to a polished cinematic portrait, realistic lighting, detailed fabric texture",
    "image_name": "source.png",
    "image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
    "count": 1,
    "options": {
      "steps": 20,
      "cfg": 4,
      "seed": 987654321,
      "sampler_name": "euler"
    }
  }
}
```

The `image` value can be a full data URI:

```text
data:image/png;base64,<BASE64_DATA>
```

or a raw base64 string:

```text
<BASE64_DATA>
```

Legacy `images` array:

```json
{
  "input": {
    "mode": "i2i",
    "prompt": "preserve identity, improve sharpness and color, clean background",
    "images": [
      {
        "name": "input_image.png",
        "image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."
      }
    ]
  }
}
```

## Synchronous Call

```bash
curl -X POST \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"input":{"mode":"t2i","prompt":"a cinematic portrait photo, natural skin texture, soft light","aspect_ratio":"1:1","options":{"steps":20,"cfg":4,"seed":123456}}}' \
  "https://api.runpod.ai/v2/${ENDPOINT_ID}/runsync"
```

## Synchronous Success Response

`/runsync` returns a completed RunPod job object. Generated images are in
`output.images`.

Default response when S3 upload is not configured:

```json
{
  "id": "sync-9f4b2f1a-0000-0000-0000-000000000000",
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

Response when S3 upload is configured:

```json
{
  "id": "sync-9f4b2f1a-0000-0000-0000-000000000000",
  "status": "COMPLETED",
  "output": {
    "images": [
      {
        "filename": "ComfyUI_00001_.png",
        "type": "s3_url",
        "data": "https://storage.example.com/image/job-id/ComfyUI_00001_.png?X-Amz-Signature=..."
      }
    ]
  },
  "delayTime": 123,
  "executionTime": 4567
}
```

Response fields:

| Field | Type | Description |
| --- | --- | --- |
| `id` | string | RunPod job ID. |
| `status` | string | `COMPLETED` for successful `/runsync` responses. |
| `output.images` | array | Generated image artifacts. |
| `output.images[].filename` | string | Filename assigned by ComfyUI. |
| `output.images[].type` | string | `base64` or `s3_url`. |
| `output.images[].data` | string | Base64 image data or a presigned image URL. |
| `output.errors` | string[] | Optional non-fatal warnings or artifact handling errors. |

If the workflow completes but produces no images, the worker may return:

```json
{
  "id": "sync-9f4b2f1a-0000-0000-0000-000000000000",
  "status": "COMPLETED",
  "output": {
    "status": "success_no_images",
    "images": []
  }
}
```

## Async Call

Submit:

```bash
curl -X POST \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"input":{"mode":"t2i","prompt":"a cinematic portrait photo, natural skin texture, soft light"}}' \
  "https://api.runpod.ai/v2/${ENDPOINT_ID}/run"
```

Initial async response:

```json
{
  "id": "a1b2c3d4-0000-0000-0000-000000000000",
  "status": "IN_QUEUE"
}
```

Poll status:

```bash
curl -X GET \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  "https://api.runpod.ai/v2/${ENDPOINT_ID}/status/a1b2c3d4-0000-0000-0000-000000000000"
```

Async status response while running:

```json
{
  "id": "a1b2c3d4-0000-0000-0000-000000000000",
  "status": "IN_PROGRESS"
}
```

Async status response when complete:

```json
{
  "id": "a1b2c3d4-0000-0000-0000-000000000000",
  "status": "COMPLETED",
  "output": {
    "images": [
      {
        "filename": "ComfyUI_00001_.png",
        "type": "base64",
        "data": "iVBORw0KGgoAAAANSUhEUg..."
      }
    ]
  }
}
```

## Error Response

Validation and runtime failures return an error in the RunPod job output. The
worker error value is usually a string:

```json
{
  "id": "sync-9f4b2f1a-0000-0000-0000-000000000000",
  "status": "COMPLETED",
  "output": {
    "error": "Missing 'prompt' parameter"
  }
}
```

Some upload failures include details:

```json
{
  "id": "sync-9f4b2f1a-0000-0000-0000-000000000000",
  "status": "COMPLETED",
  "output": {
    "error": "Failed to upload one or more input images",
    "details": [
      "Error decoding base64 for input_image.png: Incorrect padding"
    ]
  }
}
```

Common error messages:

| Error | Meaning |
| --- | --- |
| `Missing or invalid 'mode'. Supported values: 't2i', 'i2i'` | `input.mode` is missing or unsupported. |
| `Missing 'prompt' parameter` | `input.prompt` is missing or empty. |
| `'options' must be an object` | `input.options` is present but not a JSON object. |
| `'count' must be an integer` | `input.count` cannot be parsed as an integer. |
| `'count' must be >= 1` | `input.count` is less than `1`. |
| `Missing 'image' (or 'images') parameter for i2i mode` | `i2i` request is missing an input image. |
| `'images' must be a list of objects with 'name' and 'image' keys` | Legacy `images` array has the wrong shape. |
| `i2i supports at most 5 input images` | `input.images` contains more than 5 images. |
| `Unsupported model '<name>'` | Requested model preset is not configured. |
| `No runtime asset manifest found for model '<name>'` | Model preset exists nowhere in the runtime asset manifest. |
| `Failed downloading ...` | Runtime model download failed. |
| `ComfyUI server (...) not reachable after multiple retries.` | ComfyUI did not become reachable in the worker. |
| `Job processing failed` | Workflow produced no usable image output or only errors. |

## Client Integration Notes

- Use `/run` for production jobs that may exceed HTTP client timeout limits.
- If `output.images[].type` is `base64`, decode `output.images[].data` as image
  bytes.
- If `output.images[].type` is `s3_url`, download the image from
  `output.images[].data`.
- Treat S3 URLs as temporary unless your storage configuration guarantees
  longer-lived URLs.
- Store the seed sent in `input.options.seed` if users need reproducibility.
- Do not send raw ComfyUI workflow JSON; only the fields listed in this
  contract are part of the public API.
