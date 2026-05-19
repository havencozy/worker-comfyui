# Video API Contract

This document is for third-party clients that call the deployed RunPod endpoint
to generate videos. It only describes the HTTP API payloads and responses.

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
| `t2v` | Wan2.2 text-to-video | `prompt` |
| `wan22-t2v` | Wan2.2 text-to-video | `prompt` |
| `i2v` | Wan2.2 image-to-video | `prompt`, `start_frame` |
| `wan22-i2v` | Wan2.2 image-to-video | `prompt`, `start_frame` |
| `r2v` | Wan2.2 first-last-frame video | `prompt` and two frame references |
| `wan22-flf2v` | Wan2.2 first-last-frame video | `prompt` and two frame references |
| `hunyuan-t2v` | HunyuanVideo 1.5 text-to-video | `prompt` |
| `hunyuan-i2v` | HunyuanVideo 1.5 image-to-video | `prompt`, `start_frame` |

## Request Body

All requests must wrap generation parameters under `input`.

```json
{
  "input": {
    "mode": "hunyuan-t2v",
    "prompt": "A glass apple rotating on a studio table, cinematic lighting",
    "negative_prompt": "blur, low quality",
    "resolution": "720p",
    "aspect_ratio": "16:9",
    "duration": 5,
    "seed": 42,
    "generate_audio": false,
    "options": {
      "fps": 24,
      "steps": 30,
      "guidance_scale": 6,
      "length": 121
    }
  }
}
```

## Request Fields

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `input.mode` | string | yes | none | Video mode. See [Supported Modes](#supported-modes). |
| `input.prompt` | string | yes | none | Positive prompt. Must be non-empty. |
| `input.negative_prompt` | string | no | `""` | Negative prompt. |
| `input.resolution` | string | no | `720p` | `480p`, `720p`, or `1080p`. Use `480p`/`720p` for Hunyuan unless the deployment explicitly supports more. |
| `input.aspect_ratio` | string | no | `auto` | `auto`, `21:9`, `16:9`, `4:3`, `1:1`, `3:4`, `9:16`. `auto` maps to `16:9`. |
| `input.duration` | integer or string | no | `auto` | `auto` or integer seconds from `4` to `15`. Ignored when `options.length` is set. |
| `input.seed` | integer | no | generated | `0..2147483647`. |
| `input.generate_audio` | boolean | no | `false` | Accepted for compatibility. Current video workflows return silent videos. |
| `input.start_frame` | string | i2v | none | Data URI or raw base64 image. Required for `i2v`, `wan22-i2v`, `hunyuan-i2v`. |
| `input.end_frame` | string | r2v option | none | Data URI or raw base64 image. Used by `r2v`/`wan22-flf2v`. |
| `input.start_frame_name` | string | no | `start_frame.png` | Filename assigned to uploaded `start_frame`. |
| `input.end_frame_name` | string | no | `end_frame.png` | Filename assigned to uploaded `end_frame`. |
| `input.image_urls` | string[] | r2v option | `[]` | For `r2v`, first two URLs can be used as start/end frames. URLs must return an image content type. |
| `input.comfy_org_api_key` | string | no | env default | Per-request Comfy.org API key override, if a workflow uses ComfyUI API Nodes. |
| `input.api_key_comfy_org` | string | no | env default | Alias for `input.comfy_org_api_key`. |
| `input.options.fps` | integer | no | `24` | `8..30`. |
| `input.options.steps` | integer | no | `30` | `10..80`. |
| `input.options.guidance_scale` | number | no | `7.5` | `1..20`. |
| `input.options.motion_strength` | number | no | `0.5` | `0..1`. Reserved for workflows that expose motion strength. |
| `input.options.strength` | number | no | `0.6` | `0..1`. Reserved for workflows that expose strength. |
| `input.options.length` | integer | no | unset | Direct frame count, `1..450`. Overrides `duration`. |
| `input.options.seed` | integer | no | generated | Accepted when top-level `input.seed` is omitted. |

Frame count:

```text
if input.options.length is set:
  num_frames = input.options.length
  duration_sec = round(input.options.length / input.options.fps, 3)
else:
  duration_sec = 5 when input.duration is "auto", otherwise input.duration
  num_frames = duration_sec * input.options.fps
```

## Text-To-Video Payloads

Wan2.2 T2V:

```json
{
  "input": {
    "mode": "wan22-t2v",
    "prompt": "A cinematic aircraft crossing a stormy sky",
    "negative_prompt": "blur, low quality, watermark",
    "resolution": "720p",
    "aspect_ratio": "16:9",
    "duration": 4,
    "seed": 12345,
    "options": {
      "fps": 24,
      "steps": 30,
      "guidance_scale": 7.5
    }
  }
}
```

Hunyuan T2V:

```json
{
  "input": {
    "mode": "hunyuan-t2v",
    "prompt": "A glass apple rotating on a studio table, cinematic lighting",
    "negative_prompt": "blur, low quality",
    "resolution": "720p",
    "aspect_ratio": "16:9",
    "seed": 42,
    "options": {
      "fps": 24,
      "steps": 30,
      "guidance_scale": 6,
      "length": 121
    }
  }
}
```

## Image-To-Video Payloads

Inline base64 image:

```json
{
  "input": {
    "mode": "hunyuan-i2v",
    "prompt": "Preserve the subject identity and add subtle cinematic camera motion",
    "start_frame": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
    "start_frame_name": "start.png",
    "resolution": "720p",
    "aspect_ratio": "16:9",
    "options": {
      "fps": 24,
      "steps": 30,
      "guidance_scale": 6
    }
  }
}
```

The `start_frame` value can be a full data URI:

```text
data:image/png;base64,<BASE64_DATA>
```

or a raw base64 string:

```text
<BASE64_DATA>
```

## First-Last-Frame Payloads

Inline start and end frames:

```json
{
  "input": {
    "mode": "wan22-flf2v",
    "prompt": "Animate smoothly from the first frame to the last frame with natural motion",
    "start_frame": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
    "end_frame": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
    "start_frame_name": "first.png",
    "end_frame_name": "last.png",
    "resolution": "720p",
    "aspect_ratio": "16:9",
    "duration": 5,
    "options": {
      "fps": 24,
      "steps": 30
    }
  }
}
```

Remote image URLs:

```json
{
  "input": {
    "mode": "r2v",
    "prompt": "Animate smoothly from @Image1 to @Image2 with natural motion",
    "image_urls": [
      "https://example.com/start.png",
      "https://example.com/end.png"
    ],
    "resolution": "720p",
    "aspect_ratio": "16:9",
    "duration": 5,
    "options": {
      "fps": 24,
      "steps": 30
    }
  }
}
```

For `r2v`, `@ImageN` placeholders are valid only when
`input.image_urls[N - 1]` exists. `@VideoN` and `@AudioN` placeholders are not
supported.

## Synchronous Call

```bash
curl -X POST \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"input":{"mode":"hunyuan-t2v","prompt":"A glass apple rotating on a studio table","resolution":"720p","aspect_ratio":"16:9","options":{"fps":24,"steps":30,"guidance_scale":6,"length":121}}}' \
  "https://api.runpod.ai/v2/${ENDPOINT_ID}/runsync"
```

## Synchronous Success Response

`/runsync` returns a completed RunPod job object. The generated video URL is in
`output.videos[0].data`.

```json
{
  "id": "sync-9f4b2f1a-0000-0000-0000-000000000000",
  "status": "COMPLETED",
  "output": {
    "videos": [
      {
        "filename": "job-id_hunyuan_t2v_00001.mp4",
        "type": "s3_url",
        "data": "https://storage.example.com/video/job-id/job-id_hunyuan_t2v_00001.mp4?X-Amz-Signature=..."
      }
    ],
    "meta": {
      "mode": "t2v",
      "model": "hunyuanvideo-1.5",
      "seed": 42,
      "fps": 24,
      "duration_sec": 5.042,
      "num_frames": 121,
      "width": 1280,
      "height": 720,
      "warnings": []
    }
  },
  "delayTime": 128,
  "executionTime": 93214
}
```

Response fields:

| Field | Type | Description |
| --- | --- | --- |
| `id` | string | RunPod job ID. |
| `status` | string | `COMPLETED` for successful `/runsync` responses. |
| `output.videos` | array | Generated video artifacts. |
| `output.videos[].filename` | string | Generated filename. |
| `output.videos[].type` | string | `s3_url`. |
| `output.videos[].data` | string | Presigned video download URL. |
| `output.meta.mode` | string | Normalized mode: `t2v`, `i2v`, or `r2v`. |
| `output.meta.model` | string | Model used by the workflow. |
| `output.meta.seed` | integer | Actual seed used. Store this for reproducibility. |
| `output.meta.fps` | integer | Output FPS. |
| `output.meta.duration_sec` | number | Reported output duration in seconds. |
| `output.meta.num_frames` | integer | Number of frames requested. |
| `output.meta.width` | integer | Requested output width. |
| `output.meta.height` | integer | Requested output height. |
| `output.meta.warnings` | string[] | Non-fatal request warnings. |
| `output.errors` | string[] | Optional non-fatal artifact handling errors. |

## Async Call

Submit:

```bash
curl -X POST \
  -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"input":{"mode":"wan22-t2v","prompt":"A neon city street at night","resolution":"480p","aspect_ratio":"16:9","duration":4}}' \
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
    "videos": [
      {
        "filename": "job-id_wan22_t2v_00001.mp4",
        "type": "s3_url",
        "data": "https://storage.example.com/video/job-id/job-id_wan22_t2v_00001.mp4?X-Amz-Signature=..."
      }
    ],
    "meta": {
      "mode": "t2v",
      "model": "wan2.2-14b",
      "seed": 12345,
      "fps": 24,
      "duration_sec": 4,
      "num_frames": 96,
      "width": 848,
      "height": 480,
      "warnings": []
    }
  }
}
```

## Error Response

Validation and runtime failures return an `error` object.

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Missing 'prompt' parameter"
  }
}
```

Common error codes:

| Code | Meaning |
| --- | --- |
| `UNSUPPORTED_MODE` | `input.mode` is missing or not supported by this deployment. |
| `VALIDATION_ERROR` | A required field is missing or has an invalid value. |
| `UNSUPPORTED_REFERENCE_COMBINATION` | Prompt references unsupported media placeholders, such as `@Video1`. |
| `MODEL_ASSET_MISSING` | Required model files are not visible to the worker. |
| `ASSET_FETCH_FAILED` | A remote image URL could not be fetched or did not return an image. |
| `OUTPUT_NOT_FOUND` | The workflow completed but no video file was found. |

## Client Integration Notes

- Use `/run` for production jobs that may take longer than HTTP client timeout
  limits.
- Store `output.meta.seed` with each generated video if users need
  reproducibility.
- Treat `output.videos[].data` as a temporary download URL. Mirror the file to
  your own storage if you need long-term access.
- Expect `warnings` to be present but empty for normal jobs.
- Do not send raw ComfyUI workflow JSON; only the fields listed in this
  contract are part of the public API.

