# Wan2.2 Video Worker Design

## Goal

Convert this worker into a video-only RunPod ComfyUI worker for Wan2.2 14B video generation while keeping the existing RunPod serverless endpoints:

- `POST /run`
- `POST /runsync`
- `GET /status/{job_id}`
- `GET /health`

The worker will not add custom `/v1/videos/*` HTTP routes. Clients will continue sending requests under the RunPod `input` object. The handler will validate `input.mode`, select a Wan2.2 workflow, inject request fields, execute ComfyUI, upload video artifacts to S3, and return video output metadata.

## Non-Goals

- No image generation modes in the video deployment contract.
- No `t2i` or `i2i` documentation for this deployment.
- No native audio generation.
- No Wan2.2 S2V in this first implementation.
- No general video/audio-reference reasoning for `r2v`.

## External Basis

The implementation will use official ComfyUI Wan2.2 native workflow templates and model paths:

- Wan2.2 14B T2V
- Wan2.2 14B I2V
- Wan2.2 14B FLF2V

Reference: https://docs.comfy.org/tutorials/video/wan/wan2_2

The selected workflows generate silent video. Wan2.2 S2V supports image plus audio input, but it uses a different workflow and model set and is out of scope for this version.

## Request Shape

Requests keep the RunPod wrapper:

```json
{
  "input": {
    "mode": "t2v",
    "prompt": "cinematic city street at night",
    "negative_prompt": "low quality, blur",
    "resolution": "720p",
    "duration": "auto",
    "aspect_ratio": "16:9",
    "seed": 12345,
    "generate_audio": true,
    "image_urls": [],
    "video_urls": [],
    "audio_urls": [],
    "start_frame": null,
    "end_frame": null,
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

## Modes

### `t2v`

Text-to-video.

- Required: `mode`, `prompt`
- Uses: `workflows/wan2_2_14b_t2v.json`
- Ignores: `start_frame`, `end_frame`, `image_urls`, `video_urls`, `audio_urls`
- If ignored references are present, return warnings in `meta.warnings`

### `i2v`

Image-to-video.

- Required: `mode`, `prompt`, `start_frame`
- Uses: `workflows/wan2_2_14b_i2v.json`
- Optional: `end_frame` is ignored for this mode with a warning
- `start_frame` may be an HTTP(S) URL, data URI, or base64 string

### `r2v`

Reference-to-video for this deployment means Wan2.2 first-last-frame video.

- Required: `mode`, `prompt`
- Required frame pair, resolved in this order:
  - `start_frame` and `end_frame`
  - `image_urls[0]` and `image_urls[1]`
- Uses: `workflows/wan2_2_14b_flf2v.json`
- `video_urls` and `audio_urls` are validated for shape but not consumed by the workflow
- If `@VideoN` or `@AudioN` placeholders are present, validation will fail with a clear unsupported reference error because this version cannot consume video or audio references
- If `@ImageN` placeholders are present, `image_urls[N-1]` must exist

## Field Constraints

- `resolution`: enum `480p | 720p | 1080p`, default `720p`
- `duration`: `auto` or integer `4..15`, default `auto`
- `aspect_ratio`: enum `auto | 21:9 | 16:9 | 4:3 | 1:1 | 3:4 | 9:16`, default `auto`
- `generate_audio`: boolean, default `false`
- `seed`: integer `0..2147483647`, optional
- `options.fps`: integer `8..30`, default `24`
- `options.steps`: integer `10..80`, default `30`
- `options.guidance_scale`: float `1..20`, default `7.5`
- `options.motion_strength`: float `0..1`, default `0.5`
- `options.strength`: float `0..1`, default `0.6`

If `generate_audio=true`, the request remains valid but the response includes `AUDIO_NOT_SUPPORTED_BY_WORKFLOW` in `meta.warnings`. Output video is expected to be silent.

## Resolution Mapping

`aspect_ratio=auto` maps to `16:9`.

For landscape ratios (`21:9`, `16:9`, `4:3`), `resolution` sets the target height. For portrait ratios (`3:4`, `9:16`), `resolution` sets the target width. For `1:1`, `resolution` sets both sides. The computed companion side is rounded to the nearest multiple of 16.

- `480p`: target side `480`
- `720p`: target side `720`
- `1080p`: target side `1080`

The implementation keeps this mapping deterministic and exposes final `width` and `height` in response metadata.

Initial defaults:

- `480p + 16:9` -> `854x480`, rounded to model-safe dimensions
- `720p + 16:9` -> `1280x720`, rounded to model-safe dimensions
- `1080p + 16:9` -> `1920x1080`, rounded to model-safe dimensions

If a workflow or GPU target cannot reliably handle 1080p, validation returns `VALIDATION_ERROR` or a clear model-capability error instead of silently downgrading.

## Frame Mapping

- `duration=auto` means `5` seconds
- `num_frames = duration_sec * fps`
- Final frame count is rounded upward to the nearest workflow-safe frame count when Wan2.2 node constraints require it
- Response metadata must include the requested duration, final `duration_sec`, `fps`, and final `num_frames`

## Workflow Files

Add these files:

- `workflows/wan2_2_14b_t2v.json`
- `workflows/wan2_2_14b_i2v.json`
- `workflows/wan2_2_14b_flf2v.json`

The files will be based on official ComfyUI workflow templates and converted to API prompt format during implementation. The implementation uses stable node type and title based injection, with node IDs only as a fallback when the official template lacks enough metadata.

Environment overrides:

- `WAN22_T2V_WORKFLOW_PATH`
- `WAN22_I2V_WORKFLOW_PATH`
- `WAN22_R2V_WORKFLOW_PATH`

## Docker and Models

Add a Docker `MODEL_TYPE` for Wan2.2 14B, for example `wan2.2-14b`.

The downloader stage creates and populates:

- `models/diffusion_models`
- `models/text_encoders`
- `models/vae`
- `models/loras` if the selected official templates require Lightning LoRAs

Required T2V assets:

- `wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors`
- `wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors`
- `umt5_xxl_fp8_e4m3fn_scaled.safetensors`
- `wan_2.1_vae.safetensors`

Required I2V and FLF2V assets:

- `wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors`
- `wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors`
- `umt5_xxl_fp8_e4m3fn_scaled.safetensors`
- `wan_2.1_vae.safetensors`

The network volume structure remains `/runpod-volume/models/...` through `src/extra_model_paths.yaml`.

## Handler Structure

`handler.py` will be refactored around video-only helpers:

- `validate_input(job_input)`
- `_build_video_mode_input(job_input, mode)`
- `_validate_video_request(job_input, mode)`
- `_resolve_video_dimensions(resolution, aspect_ratio)`
- `_resolve_num_frames(duration, fps)`
- `_fetch_input_asset(value)`
- `_upload_video_input_images(...)`
- `_set_video_prompt_fields(...)`
- `_set_video_dimensions_and_length(...)`
- `_set_video_sampler_fields(...)`
- `_set_video_load_image_fields(...)`
- `_set_video_save_fields(...)`
- `_collect_video_outputs(...)`
- `_upload_artifact_to_s3(...)`

The existing websocket execution flow can stay mostly intact:

1. Wait for ComfyUI HTTP readiness
2. Upload input assets if needed
3. Open websocket
4. Queue workflow
5. Wait for execution completion or execution error
6. Fetch history
7. Collect output videos
8. Upload videos to S3
9. Return normalized output

## Output Shape

Successful video jobs return:

```json
{
  "videos": [
    {
      "filename": "out.mp4",
      "type": "s3_url",
      "data": "https://..."
    }
  ],
  "meta": {
    "mode": "r2v",
    "model": "wan2.2-14b",
    "seed": 12345,
    "fps": 24,
    "duration_sec": 5,
    "num_frames": 120,
    "width": 1280,
    "height": 720,
    "warnings": []
  }
}
```

The video deployment does not return `images`.

Production video deployment requires S3-compatible artifact upload configuration. If S3 is not configured, validation returns `CONFIGURATION_ERROR`. Local tests can mock the upload layer instead of returning base64 videos.

## Error Handling

Use explicit error codes internally and return them in the handler output when possible:

- `VALIDATION_ERROR`
- `UNSUPPORTED_MODE`
- `UNSUPPORTED_REFERENCE_COMBINATION`
- `ASSET_FETCH_FAILED`
- `ASSET_UPLOAD_FAILED`
- `WORKFLOW_EXECUTION_FAILED`
- `OUTPUT_NOT_FOUND`
- `S3_UPLOAD_FAILED`
- `OUT_OF_MEMORY`
- `TIMEOUT`
- `CANCELED`

Validation errors happen before ComfyUI work is queued. Workflow execution errors preserve ComfyUI node type, node id, and exception message when available.

## Health

`GET /health` remains RunPod-provided. Handler-level readiness checks ComfyUI HTTP availability before each job. Internal model preflight checks fail fast when required Wan2.2 model files are missing.

## Tests

Add or update unit tests for:

- `t2v` valid request builds the T2V workflow
- `i2v` requires `start_frame`
- `r2v` accepts `start_frame + end_frame`
- `r2v` accepts `image_urls[0] + image_urls[1]`
- `r2v` rejects missing second frame
- `@ImageN` placeholder validation
- `@VideoN` and `@AudioN` unsupported reference validation
- resolution/aspect ratio mapping
- duration/fps to frame count mapping
- `generate_audio=true` warning
- video output collection from mocked ComfyUI history
- S3 upload path for video artifacts

Integration testing with Docker requires full rebuild after handler, workflow, or Dockerfile changes because these files are baked into the image.

## Deployment Notes

Build with `--platform linux/amd64` for RunPod deployment.

This deployment is separate from the current image worker deployment. The README and API docs make the video-only contract clear to avoid clients sending image modes to the Wan2.2 worker.
