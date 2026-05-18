# API Testing Guide

> Wan2.2 video quick curls are documented below. Set `RUNPOD_API_KEY` and `ENDPOINT_ID`, then use `/runsync` for blocking tests or `/run` plus `/status/<job_id>` for async tests.

This worker exposes RunPod serverless endpoints and accepts a simplified custom input payload. Clients do not send raw ComfyUI workflow JSON anymore.

## Wan2.2 Video Payload Contract

All requests must wrap the custom payload under `input`.

```json
{
  "input": {
    "mode": "t2v",
    "prompt": "A slow dolly shot through a neon city street at night",
    "negative_prompt": "low quality, blur",
    "resolution": "480p",
    "aspect_ratio": "16:9",
    "duration": 4,
    "seed": 12345,
    "generate_audio": false,
    "options": {
      "fps": 16,
      "steps": 20,
      "guidance_scale": 7.5,
      "motion_strength": 0.5,
      "strength": 0.6,
      "length": 64
    }
  }
}
```

### Supported Modes

| Mode | Aliases | Required fields | Notes |
| --- | --- | --- | --- |
| `t2v` | `wan22-t2v` | `prompt` | Text-to-video. `start_frame`, `end_frame`, and reference URL arrays are ignored with warnings. |
| `i2v` | `wan22-i2v` | `prompt`, `start_frame` | Image-to-video. `start_frame_name` controls the uploaded frame filename. |
| `r2v` | `wan22-flf2v` | `prompt` plus two frame refs | First-last-frame video. Send `start_frame` and `end_frame`, or at least two `image_urls`. |

`r2v` prompt placeholders support `@ImageN` only when `image_urls[N-1]` exists. `@VideoN` and `@AudioN` references are rejected for this Wan2.2 FLF2V deployment.

### Request Fields

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `input.mode` | string | yes | `t2v`, `i2v`, `r2v`, or aliases `wan22-t2v`, `wan22-i2v`, `wan22-flf2v`. |
| `input.prompt` | string | yes | Positive prompt injected into the selected Wan2.2 workflow. |
| `input.negative_prompt` | string | no | Negative prompt. Defaults to an empty string. |
| `input.resolution` | string | no | `480p`, `720p`, `1080p`. Defaults to `720p`. |
| `input.aspect_ratio` | string | no | `auto`, `21:9`, `16:9`, `4:3`, `1:1`, `3:4`, `9:16`. `auto` maps to `16:9`. |
| `input.duration` | string or integer | no | `auto` or integer seconds `4..15`. `auto` means 5 seconds. Ignored when `options.length` is set. |
| `input.seed` | integer | no | `0..2147483647`. If omitted, the worker generates one. |
| `input.generate_audio` | boolean | no | Accepted for compatibility. Wan2.2 video workflows do not generate audio; `true` adds `AUDIO_NOT_SUPPORTED_BY_WORKFLOW` to `meta.warnings`. |
| `input.start_frame` | string | `i2v`; `r2v` option | Data URI or raw base64 frame. Use `image_urls` for remote HTTP(S) frames. |
| `input.end_frame` | string | `r2v` option | Data URI or raw base64 frame. Use `image_urls` for remote HTTP(S) frames. |
| `input.start_frame_name` | string | no | Filename used when uploading `start_frame`. Defaults to `start_frame.png`. |
| `input.end_frame_name` | string | no | Filename used when uploading `end_frame`. Defaults to `end_frame.png`. |
| `input.image_urls` | array | `r2v` option | First two URLs are used as start/end frames when inline frame fields are not supplied. |
| `input.video_urls` | array | no | Not consumed by this Wan2.2 FLF2V deployment. `@VideoN` placeholders are rejected. |
| `input.audio_urls` | array | no | Not consumed by this Wan2.2 FLF2V deployment. `@AudioN` placeholders are rejected. |
| `input.comfy_org_api_key` / `input.api_key_comfy_org` | string | no | Optional per-request Comfy.org API key override for workflows that use ComfyUI API Nodes. |
| `input.options.fps` | integer | no | `8..30`. Defaults to `24`. |
| `input.options.steps` | integer | no | `10..80`. Defaults to `30`. Wan2.2 dual samplers split this into high-noise and low-noise ranges. |
| `input.options.guidance_scale` | number | no | `1..20`. Defaults to `7.5`; maps to sampler `cfg`. |
| `input.options.motion_strength` | number | no | `0..1`. Defaults to `0.5`. Reserved for workflows that expose motion controls. |
| `input.options.strength` | number | no | `0..1`. Defaults to `0.6`. Reserved for workflows that expose strength controls. |
| `input.options.length` | integer | no | Direct frame count override, `1..450`. When set, `duration_sec = length / fps`. |

### Output Shape

Successful jobs return video artifacts only. This video branch does not return still-frame artifacts.

```json
{
  "id": "sync-...",
  "status": "COMPLETED",
  "output": {
    "videos": [
      {
        "filename": "job-id_wan22_t2v_00001_.mp4",
        "type": "s3_url",
        "data": "https://..."
      }
    ],
    "meta": {
      "mode": "t2v",
      "model": "wan2.2-14b",
      "seed": 12345,
      "fps": 16,
      "duration_sec": 4,
      "num_frames": 64,
      "width": 848,
      "height": 480,
      "warnings": []
    }
  }
}
```

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
  -d '{"input":{"mode":"wan22-i2v","prompt":"Preserve the subject identity, add subtle cinematic camera motion","start_frame":"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...","start_frame_name":"start.png","resolution":"720p","aspect_ratio":"16:9","duration":4,"options":{"fps":24,"steps":30,"guidance_scale":7.5}}}' \
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

## Common Errors

`Missing or invalid 'mode'. Supported values: 't2v', 'i2v', 'r2v', 'wan22-t2v', 'wan22-i2v', 'wan22-flf2v'`

The request body is missing `input.mode`, or the endpoint is receiving only the inner object without the RunPod `input` wrapper.

`Missing 'prompt' parameter`

Send `input.prompt`.

`Missing 'start_frame' parameter for i2v mode`

For `mode: "i2v"`, send `input.start_frame`.

`r2v mode requires two frame references via start_frame/end_frame or image_urls[0]/image_urls[1]`

For `mode: "r2v"`, send start and end frames through inline fields or the first two `image_urls`.

`MODEL_ASSET_MISSING`

Wan2.2 model files are missing from the configured model roots. Preload the required files under `/runpod-volume/models/...` or set `WAN22_MODEL_ROOTS`.

`OUTPUT_NOT_FOUND`

ComfyUI completed but the worker could not find a video artifact in history or the output directory. Check worker logs for `Full history output key summary` and `Video output scan complete`.
