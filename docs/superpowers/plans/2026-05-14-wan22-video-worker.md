# Wan2.2 Video Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert this RunPod ComfyUI worker into a video-only Wan2.2 14B worker that accepts `t2v`, `i2v`, and `r2v` modes and returns S3 video artifacts.

**Architecture:** Keep the existing RunPod `/run`, `/runsync`, `/status`, and `/health` endpoints. Replace the handler input contract with video-only validation, load one of three Wan2.2 workflow templates, inject normalized video parameters, execute ComfyUI through the existing websocket flow, collect video outputs, and upload the final files through the existing RunPod S3 helper.

**Tech Stack:** Python 3.12, `unittest`, RunPod serverless SDK, ComfyUI HTTP and websocket APIs, official ComfyUI Wan2.2 native workflows, Docker.

---

## File Structure

- Modify `handler.py`: video-only validation, Wan2.2 workflow selection, request normalization, input frame upload, workflow field injection, video output collection, S3 artifact upload.
- Modify `tests/test_handler.py`: replace image-mode validation expectations with video-mode tests and add output collection/upload tests.
- Create `test_resources/workflows/wan22_video_test_t2v.json`: compact API-format fixture for T2V injection tests.
- Create `test_resources/workflows/wan22_video_test_i2v.json`: compact API-format fixture for I2V injection tests.
- Create `test_resources/workflows/wan22_video_test_flf2v.json`: compact API-format fixture for R2V/FLF2V injection tests.
- Create `workflows/wan2_2_14b_t2v.json`: production Wan2.2 14B T2V API-format workflow.
- Create `workflows/wan2_2_14b_i2v.json`: production Wan2.2 14B I2V API-format workflow.
- Create `workflows/wan2_2_14b_flf2v.json`: production Wan2.2 14B FLF2V API-format workflow.
- Modify `Dockerfile`: add `MODEL_TYPE=wan2.2-14b` downloads and create model directories required by Wan2.2.
- Modify `docker-bake.hcl`: add a `wan2.2-14b` target if this repo is still publishing variant images from bake.
- Modify `README.md`: document the video-only RunPod input and output contract.
- Modify `docs/configuration.md`: document Wan2.2 workflow env vars and S3 requirement.
- Modify `test_input.json`: replace image generation sample with a video sample.

Keep the implementation inside `handler.py` because the current project keeps handler behavior in one file and the change is scoped to this deployment. Do not introduce a web framework or custom `/v1/videos/*` routes.

---

### Task 1: Add Video Workflow Test Fixtures

**Files:**
- Create: `test_resources/workflows/wan22_video_test_t2v.json`
- Create: `test_resources/workflows/wan22_video_test_i2v.json`
- Create: `test_resources/workflows/wan22_video_test_flf2v.json`

- [ ] **Step 1: Create the T2V API-format fixture**

Create `test_resources/workflows/wan22_video_test_t2v.json`:

```json
{
  "6": {
    "class_type": "CLIPTextEncode",
    "_meta": {"title": "CLIP Text Encode (Positive Prompt)"},
    "inputs": {"text": "old positive", "clip": ["38", 0]}
  },
  "7": {
    "class_type": "CLIPTextEncode",
    "_meta": {"title": "CLIP Text Encode (Negative Prompt)"},
    "inputs": {"text": "old negative", "clip": ["38", 0]}
  },
  "38": {
    "class_type": "CLIPLoader",
    "inputs": {
      "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
      "type": "wan",
      "device": "default"
    }
  },
  "55": {
    "class_type": "EmptyHunyuanLatentVideo",
    "inputs": {"width": 640, "height": 640, "length": 81, "batch_size": 1}
  },
  "57": {
    "class_type": "KSamplerAdvanced",
    "inputs": {
      "noise_seed": 1,
      "steps": 20,
      "cfg": 5.0,
      "sampler_name": "euler",
      "scheduler": "simple"
    }
  },
  "58": {
    "class_type": "SaveVideo",
    "inputs": {"filename_prefix": "video/ComfyUI", "fps": 16, "format": "auto"}
  }
}
```

- [ ] **Step 2: Create the I2V API-format fixture**

Create `test_resources/workflows/wan22_video_test_i2v.json`:

```json
{
  "6": {
    "class_type": "CLIPTextEncode",
    "_meta": {"title": "CLIP Text Encode (Positive Prompt)"},
    "inputs": {"text": "old positive", "clip": ["38", 0]}
  },
  "7": {
    "class_type": "CLIPTextEncode",
    "_meta": {"title": "CLIP Text Encode (Negative Prompt)"},
    "inputs": {"text": "old negative", "clip": ["38", 0]}
  },
  "56": {
    "class_type": "LoadImage",
    "inputs": {"image": "example.png", "upload": "image"}
  },
  "81": {
    "class_type": "Wan22ImageToVideoLatent",
    "inputs": {"width": 640, "height": 640, "length": 81, "batch_size": 1, "start_image": ["56", 0]}
  },
  "57": {
    "class_type": "KSamplerAdvanced",
    "inputs": {
      "noise_seed": 1,
      "steps": 20,
      "cfg": 5.0,
      "sampler_name": "euler",
      "scheduler": "simple"
    }
  },
  "58": {
    "class_type": "SaveVideo",
    "inputs": {"filename_prefix": "video/ComfyUI", "fps": 16, "format": "auto"}
  }
}
```

- [ ] **Step 3: Create the FLF2V API-format fixture**

Create `test_resources/workflows/wan22_video_test_flf2v.json`:

```json
{
  "6": {
    "class_type": "CLIPTextEncode",
    "_meta": {"title": "CLIP Text Encode (Positive Prompt)"},
    "inputs": {"text": "old positive", "clip": ["38", 0]}
  },
  "7": {
    "class_type": "CLIPTextEncode",
    "_meta": {"title": "CLIP Text Encode (Negative Prompt)"},
    "inputs": {"text": "old negative", "clip": ["38", 0]}
  },
  "62": {
    "class_type": "LoadImage",
    "_meta": {"title": "Start Frame"},
    "inputs": {"image": "start.png", "upload": "image"}
  },
  "68": {
    "class_type": "LoadImage",
    "_meta": {"title": "End Frame"},
    "inputs": {"image": "end.png", "upload": "image"}
  },
  "81": {
    "class_type": "WanFirstLastFrameToVideo",
    "inputs": {"width": 640, "height": 640, "length": 81, "batch_size": 1}
  },
  "57": {
    "class_type": "KSamplerAdvanced",
    "inputs": {
      "noise_seed": 1,
      "steps": 20,
      "cfg": 5.0,
      "sampler_name": "euler",
      "scheduler": "simple"
    }
  },
  "58": {
    "class_type": "SaveVideo",
    "inputs": {"filename_prefix": "video/ComfyUI", "fps": 16, "format": "auto"}
  }
}
```

- [ ] **Step 4: Validate fixture JSON**

Run:

```bash
python -m json.tool test_resources/workflows/wan22_video_test_t2v.json >/dev/null
python -m json.tool test_resources/workflows/wan22_video_test_i2v.json >/dev/null
python -m json.tool test_resources/workflows/wan22_video_test_flf2v.json >/dev/null
```

Expected: all commands exit `0`.

- [ ] **Step 5: Commit**

```bash
git add test_resources/workflows/wan22_video_test_t2v.json test_resources/workflows/wan22_video_test_i2v.json test_resources/workflows/wan22_video_test_flf2v.json
git commit -m "test: add Wan2.2 video workflow fixtures"
```

---

### Task 2: Write Video-Only Validation Tests

**Files:**
- Modify: `tests/test_handler.py`
- Test: `tests/test_handler.py`

- [ ] **Step 1: Replace old image-mode validation tests with video-mode tests**

In `tests/test_handler.py`, replace the existing `test_valid_t2i_input_builds_workflow_from_template`, `test_valid_i2i_input_uploads_image_and_preserves_source_dimensions_by_default`, `test_valid_i2i_input_accepts_legacy_images_array_for_upload_only`, `test_valid_json_string_input`, `test_input_missing_mode`, `test_input_missing_prompt`, `test_i2i_missing_image`, and `test_i2i_with_invalid_images_structure` methods with these tests:

```python
    def setUp(self):
        self.workflow_env = patch.dict(
            os.environ,
            {
                "WAN22_T2V_WORKFLOW_PATH": os.path.join(
                    REPO_ROOT, "test_resources/workflows/wan22_video_test_t2v.json"
                ),
                "WAN22_I2V_WORKFLOW_PATH": os.path.join(
                    REPO_ROOT, "test_resources/workflows/wan22_video_test_i2v.json"
                ),
                "WAN22_R2V_WORKFLOW_PATH": os.path.join(
                    REPO_ROOT, "test_resources/workflows/wan22_video_test_flf2v.json"
                ),
                "BUCKET_ENDPOINT_URL": "https://bucket.example.com",
            },
        )
        self.workflow_env.start()
        handler._refresh_runtime_config()

    def tearDown(self):
        self.workflow_env.stop()
        handler._refresh_runtime_config()

    def test_valid_t2v_input_builds_wan22_t2v_workflow(self):
        input_data = {
            "mode": "t2v",
            "prompt": "a red aircraft crossing a storm",
            "negative_prompt": "blur",
            "resolution": "720p",
            "aspect_ratio": "16:9",
            "duration": 5,
            "seed": 42,
            "options": {"fps": 24, "steps": 30, "guidance_scale": 7.5},
        }

        validated_data, error = handler.validate_input(input_data)

        self.assertIsNone(error)
        workflow = validated_data["workflow"]
        self.assertEqual(workflow["6"]["inputs"]["text"], input_data["prompt"])
        self.assertEqual(workflow["7"]["inputs"]["text"], input_data["negative_prompt"])
        self.assertEqual(workflow["55"]["inputs"]["width"], 1280)
        self.assertEqual(workflow["55"]["inputs"]["height"], 720)
        self.assertEqual(workflow["55"]["inputs"]["length"], 120)
        self.assertEqual(workflow["57"]["inputs"]["noise_seed"], 42)
        self.assertEqual(workflow["57"]["inputs"]["steps"], 30)
        self.assertEqual(workflow["57"]["inputs"]["cfg"], 7.5)
        self.assertEqual(workflow["58"]["inputs"]["fps"], 24)
        self.assertEqual(validated_data["meta"]["mode"], "t2v")
        self.assertEqual(validated_data["meta"]["num_frames"], 120)
        self.assertEqual(validated_data["meta"]["warnings"], [])

    def test_valid_json_string_input_for_t2v(self):
        input_data = '{"mode": "t2v", "prompt": "clean cinematic motion"}'

        validated_data, error = handler.validate_input(input_data)

        self.assertIsNone(error)
        self.assertEqual(
            validated_data["workflow"]["6"]["inputs"]["text"],
            "clean cinematic motion",
        )

    def test_t2v_generate_audio_adds_warning(self):
        input_data = {
            "mode": "t2v",
            "prompt": "silent mountains",
            "generate_audio": True,
        }

        validated_data, error = handler.validate_input(input_data)

        self.assertIsNone(error)
        self.assertIn(
            "AUDIO_NOT_SUPPORTED_BY_WORKFLOW",
            validated_data["meta"]["warnings"],
        )

    def test_valid_i2v_requires_and_wires_start_frame(self):
        input_data = {
            "mode": "i2v",
            "prompt": "a portrait turns toward camera",
            "start_frame": "data:image/png;base64,ZmFrZQ==",
        }

        validated_data, error = handler.validate_input(input_data)

        self.assertIsNone(error)
        self.assertEqual(
            validated_data["images"],
            [{"name": "start_frame.png", "image": input_data["start_frame"]}],
        )
        self.assertEqual(
            validated_data["workflow"]["56"]["inputs"]["image"],
            "start_frame.png",
        )

    def test_i2v_missing_start_frame_fails(self):
        validated_data, error = handler.validate_input(
            {"mode": "i2v", "prompt": "move"}
        )

        self.assertIsNone(validated_data)
        self.assertEqual(error["code"], "VALIDATION_ERROR")
        self.assertIn("start_frame", error["message"])

    def test_valid_r2v_wires_start_and_end_frames(self):
        input_data = {
            "mode": "r2v",
            "prompt": "transform between frames",
            "start_frame": "data:image/png;base64,c3RhcnQ=",
            "end_frame": "data:image/png;base64,ZW5k",
        }

        validated_data, error = handler.validate_input(input_data)

        self.assertIsNone(error)
        self.assertEqual(
            validated_data["images"],
            [
                {"name": "start_frame.png", "image": input_data["start_frame"]},
                {"name": "end_frame.png", "image": input_data["end_frame"]},
            ],
        )
        self.assertEqual(
            validated_data["workflow"]["62"]["inputs"]["image"],
            "start_frame.png",
        )
        self.assertEqual(
            validated_data["workflow"]["68"]["inputs"]["image"],
            "end_frame.png",
        )

    def test_r2v_accepts_first_two_image_urls(self):
        input_data = {
            "mode": "r2v",
            "prompt": "transform @Image1 into @Image2",
            "image_urls": [
                "https://example.com/start.png",
                "https://example.com/end.png",
            ],
        }

        validated_data, error = handler.validate_input(input_data)

        self.assertIsNone(error)
        self.assertEqual(
            validated_data["remote_images"],
            [
                {"name": "start_frame.png", "url": "https://example.com/start.png"},
                {"name": "end_frame.png", "url": "https://example.com/end.png"},
            ],
        )

    def test_r2v_missing_second_frame_fails(self):
        validated_data, error = handler.validate_input(
            {
                "mode": "r2v",
                "prompt": "transform",
                "image_urls": ["https://example.com/start.png"],
            }
        )

        self.assertIsNone(validated_data)
        self.assertEqual(error["code"], "VALIDATION_ERROR")
        self.assertIn("two frame references", error["message"])

    def test_r2v_image_placeholder_requires_matching_image_url(self):
        validated_data, error = handler.validate_input(
            {
                "mode": "r2v",
                "prompt": "move from @Image3 to @Image1",
                "image_urls": [
                    "https://example.com/start.png",
                    "https://example.com/end.png",
                ],
            }
        )

        self.assertIsNone(validated_data)
        self.assertEqual(error["code"], "VALIDATION_ERROR")
        self.assertIn("@Image3", error["message"])

    def test_r2v_video_placeholder_is_unsupported(self):
        validated_data, error = handler.validate_input(
            {
                "mode": "r2v",
                "prompt": "follow @Video1",
                "image_urls": [
                    "https://example.com/start.png",
                    "https://example.com/end.png",
                ],
                "video_urls": ["https://example.com/ref.mp4"],
            }
        )

        self.assertIsNone(validated_data)
        self.assertEqual(error["code"], "UNSUPPORTED_REFERENCE_COMBINATION")
        self.assertIn("@Video1", error["message"])

    def test_legacy_image_modes_are_not_supported(self):
        validated_data, error = handler.validate_input(
            {"mode": "t2i", "prompt": "old image mode"}
        )

        self.assertIsNone(validated_data)
        self.assertEqual(error["code"], "UNSUPPORTED_MODE")
```

- [ ] **Step 2: Run tests and verify they fail for missing implementation**

Run:

```bash
python -m unittest tests.test_handler.TestRunpodWorkerComfy -v
```

Expected: failures mention missing `handler._refresh_runtime_config`, unsupported `t2v`, or string error shape mismatch.

- [ ] **Step 3: Commit failing tests and fixtures only**

```bash
git add tests/test_handler.py test_resources/workflows/wan22_video_test_t2v.json test_resources/workflows/wan22_video_test_i2v.json test_resources/workflows/wan22_video_test_flf2v.json
git commit -m "test: define video-only handler contract"
```

---

### Task 3: Implement Video Request Normalization

**Files:**
- Modify: `handler.py`
- Test: `tests/test_handler.py`

- [ ] **Step 1: Add constants and runtime config refresh**

In `handler.py`, replace the Flux workflow path constants with:

```python
WAN22_MODEL_NAME = "wan2.2-14b"
VIDEO_MODES = {"t2v", "i2v", "r2v"}
RESOLUTION_PRESETS = {"480p": 480, "720p": 720, "1080p": 1080}
VIDEO_ASPECT_RATIOS = {
    "21:9": (21, 9),
    "16:9": (16, 9),
    "4:3": (4, 3),
    "1:1": (1, 1),
    "3:4": (3, 4),
    "9:16": (9, 16),
}
DEFAULT_NEGATIVE_PROMPT = ""
DEFAULT_VIDEO_OPTIONS = {
    "fps": 24,
    "steps": 30,
    "guidance_scale": 7.5,
    "motion_strength": 0.5,
    "strength": 0.6,
}


def _refresh_runtime_config():
    global WAN22_T2V_WORKFLOW_PATH
    global WAN22_I2V_WORKFLOW_PATH
    global WAN22_R2V_WORKFLOW_PATH

    WAN22_T2V_WORKFLOW_PATH = os.environ.get(
        "WAN22_T2V_WORKFLOW_PATH",
        os.path.join(WORKFLOW_DIR, "wan2_2_14b_t2v.json"),
    )
    WAN22_I2V_WORKFLOW_PATH = os.environ.get(
        "WAN22_I2V_WORKFLOW_PATH",
        os.path.join(WORKFLOW_DIR, "wan2_2_14b_i2v.json"),
    )
    WAN22_R2V_WORKFLOW_PATH = os.environ.get(
        "WAN22_R2V_WORKFLOW_PATH",
        os.path.join(WORKFLOW_DIR, "wan2_2_14b_flf2v.json"),
    )


_refresh_runtime_config()
```

- [ ] **Step 2: Add structured error helper**

Add below `_load_workflow_template`:

```python
def _error(code, message):
    return {"code": code, "message": message}
```

- [ ] **Step 3: Replace `validate_input` mode dispatch**

Replace `validate_input` body after JSON parsing with:

```python
    if not isinstance(job_input, dict):
        return None, _error("VALIDATION_ERROR", "Input must be an object")

    mode = job_input.get("mode")
    if mode in VIDEO_MODES:
        return _build_video_mode_input(job_input, mode)

    if mode in {"t2i", "i2i"}:
        return None, _error(
            "UNSUPPORTED_MODE",
            "This deployment supports video modes only: 't2v', 'i2v', 'r2v'",
        )

    return None, _error(
        "UNSUPPORTED_MODE",
        "Missing or invalid 'mode'. Supported values: 't2v', 'i2v', 'r2v'",
    )
```

Keep the existing `None` and invalid JSON checks, but change their errors to structured objects:

```python
    if job_input is None:
        return None, _error("VALIDATION_ERROR", "Please provide input")
```

```python
        except json.JSONDecodeError:
            return None, _error("VALIDATION_ERROR", "Invalid JSON format in input")
```

- [ ] **Step 4: Add deterministic dimension and frame helpers**

Add:

```python
def _round_to_multiple(value, multiple=16):
    return int(round(value / multiple) * multiple)


def _resolve_video_dimensions(resolution="720p", aspect_ratio="auto"):
    resolution = resolution or "720p"
    aspect_ratio = "16:9" if aspect_ratio in (None, "auto") else str(aspect_ratio)

    if resolution not in RESOLUTION_PRESETS:
        raise ValueError("'resolution' must be one of: 480p, 720p, 1080p")
    if aspect_ratio not in VIDEO_ASPECT_RATIOS:
        raise ValueError(
            "'aspect_ratio' must be one of: auto, 21:9, 16:9, 4:3, 1:1, 3:4, 9:16"
        )

    target = RESOLUTION_PRESETS[resolution]
    ratio_w, ratio_h = VIDEO_ASPECT_RATIOS[aspect_ratio]

    if ratio_w > ratio_h:
        height = target
        width = _round_to_multiple(target * ratio_w / ratio_h)
    elif ratio_h > ratio_w:
        width = target
        height = _round_to_multiple(target * ratio_h / ratio_w)
    else:
        width = target
        height = target

    return width, height


def _resolve_duration_sec(duration):
    if duration in (None, "auto"):
        return 5
    try:
        duration_sec = int(duration)
    except (TypeError, ValueError):
        raise ValueError("'duration' must be 'auto' or an integer from 4 to 15")
    if duration_sec < 4 or duration_sec > 15:
        raise ValueError("'duration' must be between 4 and 15 seconds")
    return duration_sec


def _resolve_num_frames(duration_sec, fps):
    return int(duration_sec) * int(fps)
```

- [ ] **Step 5: Add option and prompt validation helpers**

Add:

```python
def _require_prompt(job_input):
    prompt = job_input.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Missing 'prompt' parameter")
    return prompt


def _normalize_video_options(job_input):
    options = dict(DEFAULT_VIDEO_OPTIONS)
    raw_options = job_input.get("options") or {}
    if not isinstance(raw_options, dict):
        raise ValueError("'options' must be an object")
    options.update(raw_options)

    fps = int(options["fps"])
    steps = int(options["steps"])
    guidance_scale = float(options["guidance_scale"])
    motion_strength = float(options["motion_strength"])
    strength = float(options["strength"])

    if fps < 8 or fps > 30:
        raise ValueError("'options.fps' must be between 8 and 30")
    if steps < 10 or steps > 80:
        raise ValueError("'options.steps' must be between 10 and 80")
    if guidance_scale < 1 or guidance_scale > 20:
        raise ValueError("'options.guidance_scale' must be between 1 and 20")
    if motion_strength < 0 or motion_strength > 1:
        raise ValueError("'options.motion_strength' must be between 0 and 1")
    if strength < 0 or strength > 1:
        raise ValueError("'options.strength' must be between 0 and 1")

    return {
        "fps": fps,
        "steps": steps,
        "guidance_scale": guidance_scale,
        "motion_strength": motion_strength,
        "strength": strength,
    }


def _normalize_seed(job_input):
    if job_input.get("seed") is None:
        return int(time.time_ns() % 2147483647)
    seed = int(job_input["seed"])
    if seed < 0 or seed > 2147483647:
        raise ValueError("'seed' must be between 0 and 2147483647")
    return seed
```

- [ ] **Step 6: Add `_validate_video_request`**

Add:

```python
def _validate_video_request(job_input, mode):
    prompt = _require_prompt(job_input)
    options = _normalize_video_options(job_input)
    width, height = _resolve_video_dimensions(
        job_input.get("resolution", "720p"),
        job_input.get("aspect_ratio", "auto"),
    )
    duration_sec = _resolve_duration_sec(job_input.get("duration", "auto"))
    num_frames = _resolve_num_frames(duration_sec, options["fps"])
    seed = _normalize_seed(job_input)

    warnings = []
    if bool(job_input.get("generate_audio", False)):
        warnings.append("AUDIO_NOT_SUPPORTED_BY_WORKFLOW")

    return {
        "mode": mode,
        "prompt": prompt,
        "negative_prompt": job_input.get("negative_prompt", DEFAULT_NEGATIVE_PROMPT),
        "width": width,
        "height": height,
        "duration_sec": duration_sec,
        "num_frames": num_frames,
        "seed": seed,
        "options": options,
        "warnings": warnings,
    }
```

- [ ] **Step 7: Run validation tests**

Run:

```bash
python -m unittest tests.test_handler.TestRunpodWorkerComfy.test_legacy_image_modes_are_not_supported \
  tests.test_handler.TestRunpodWorkerComfy.test_valid_json_string_input_for_t2v \
  tests.test_handler.TestRunpodWorkerComfy.test_t2v_generate_audio_adds_warning -v
```

Expected: these tests pass after `_build_video_mode_input` exists in the next step. If they fail only because `_build_video_mode_input` is missing, continue to Task 4 before committing.

---

### Task 4: Implement Workflow Selection and Injection

**Files:**
- Modify: `handler.py`
- Test: `tests/test_handler.py`

- [ ] **Step 1: Add workflow path selector**

Add:

```python
def _video_workflow_path(mode):
    if mode == "t2v":
        return WAN22_T2V_WORKFLOW_PATH
    if mode == "i2v":
        return WAN22_I2V_WORKFLOW_PATH
    if mode == "r2v":
        return WAN22_R2V_WORKFLOW_PATH
    raise ValueError(f"Unsupported video mode '{mode}'")
```

- [ ] **Step 2: Add placeholder validation**

Add:

```python
def _extract_placeholders(prompt, prefix):
    markers = []
    search = f"@{prefix}"
    start = 0
    while True:
        idx = prompt.find(search, start)
        if idx == -1:
            break
        pos = idx + len(search)
        digits = []
        while pos < len(prompt) and prompt[pos].isdigit():
            digits.append(prompt[pos])
            pos += 1
        if digits:
            markers.append(int("".join(digits)))
        start = pos
    return markers


def _validate_reference_placeholders(job_input, prompt):
    image_urls = job_input.get("image_urls") or []
    if image_urls and not isinstance(image_urls, list):
        raise ValueError("'image_urls' must be an array")
    for marker in _extract_placeholders(prompt, "Image"):
        if marker < 1 or marker > len(image_urls):
            raise ValueError(f"Prompt references @Image{marker}, but image_urls[{marker - 1}] is missing")

    for marker in _extract_placeholders(prompt, "Video"):
        raise RuntimeError(f"@Video{marker} references are not supported by this Wan2.2 FLF2V deployment")

    for marker in _extract_placeholders(prompt, "Audio"):
        raise RuntimeError(f"@Audio{marker} references are not supported by this Wan2.2 FLF2V deployment")
```

- [ ] **Step 3: Add frame reference resolver**

Add:

```python
def _frame_assets_for_mode(job_input, mode, prompt):
    _validate_reference_placeholders(job_input, prompt)

    if mode == "t2v":
        warnings = []
        for field in ("start_frame", "end_frame", "image_urls", "video_urls", "audio_urls"):
            if job_input.get(field):
                warnings.append(f"{field.upper()}_IGNORED_BY_T2V")
        return [], [], warnings

    if mode == "i2v":
        start_frame = job_input.get("start_frame")
        if not start_frame:
            raise ValueError("Missing 'start_frame' parameter for i2v mode")
        warnings = []
        if job_input.get("end_frame"):
            warnings.append("END_FRAME_IGNORED_BY_I2V")
        return [{"name": "start_frame.png", "image": start_frame}], [], warnings

    start_frame = job_input.get("start_frame")
    end_frame = job_input.get("end_frame")
    if start_frame and end_frame:
        return [
            {"name": "start_frame.png", "image": start_frame},
            {"name": "end_frame.png", "image": end_frame},
        ], [], []

    image_urls = job_input.get("image_urls") or []
    if len(image_urls) >= 2:
        return [], [
            {"name": "start_frame.png", "url": image_urls[0]},
            {"name": "end_frame.png", "url": image_urls[1]},
        ], []

    raise ValueError("r2v mode requires two frame references via start_frame/end_frame or image_urls[0]/image_urls[1]")
```

- [ ] **Step 4: Add workflow injection helpers**

Add:

```python
def _set_video_dimensions_and_length(workflow, width, height, num_frames):
    for node in workflow.values():
        inputs = node.get("inputs", {})
        class_type = node.get("class_type", "")
        if class_type in {
            "EmptyHunyuanLatentVideo",
            "Wan22ImageToVideoLatent",
            "WanFirstLastFrameToVideo",
        }:
            if "width" in inputs:
                inputs["width"] = int(width)
            if "height" in inputs:
                inputs["height"] = int(height)
            if "length" in inputs:
                inputs["length"] = int(num_frames)
            if "batch_size" in inputs:
                inputs["batch_size"] = 1


def _set_video_sampler_fields(workflow, seed, options):
    for node in workflow.values():
        inputs = node.get("inputs", {})
        class_type = node.get("class_type", "")
        if class_type in {"KSampler", "KSamplerAdvanced"}:
            if "seed" in inputs:
                inputs["seed"] = int(seed)
            if "noise_seed" in inputs:
                inputs["noise_seed"] = int(seed)
            if "steps" in inputs:
                inputs["steps"] = int(options["steps"])
            if "cfg" in inputs:
                inputs["cfg"] = float(options["guidance_scale"])


def _set_video_save_fields(workflow, mode, fps):
    for node in workflow.values():
        inputs = node.get("inputs", {})
        class_type = node.get("class_type", "")
        if class_type == "SaveVideo":
            if "filename_prefix" in inputs:
                inputs["filename_prefix"] = f"video/wan22_{mode}"
            if "fps" in inputs:
                inputs["fps"] = int(fps)


def _set_video_load_image_fields(workflow, mode):
    load_images = [
        (node_id, node)
        for node_id, node in workflow.items()
        if node.get("class_type") == "LoadImage"
    ]
    if mode == "i2v" and load_images:
        load_images[0][1].setdefault("inputs", {})["image"] = "start_frame.png"
        return
    if mode == "r2v":
        for node_id, node in load_images:
            title = ((node.get("_meta") or {}).get("title", "")).lower()
            if "end" in title or "last" in title:
                node.setdefault("inputs", {})["image"] = "end_frame.png"
            else:
                node.setdefault("inputs", {})["image"] = "start_frame.png"
```

- [ ] **Step 5: Add `_build_video_mode_input`**

Add:

```python
def _build_video_mode_input(job_input, mode):
    try:
        normalized = _validate_video_request(job_input, mode)
        images, remote_images, asset_warnings = _frame_assets_for_mode(
            job_input, mode, normalized["prompt"]
        )
        workflow = _load_workflow_template(_video_workflow_path(mode))

        _set_prompt_fields(
            workflow,
            prompt=normalized["prompt"],
            negative_prompt=normalized["negative_prompt"],
        )
        _set_video_dimensions_and_length(
            workflow,
            normalized["width"],
            normalized["height"],
            normalized["num_frames"],
        )
        _set_video_sampler_fields(
            workflow,
            normalized["seed"],
            normalized["options"],
        )
        _set_video_save_fields(workflow, mode, normalized["options"]["fps"])
        _set_video_load_image_fields(workflow, mode)

        warnings = normalized["warnings"] + asset_warnings
        meta = {
            "mode": mode,
            "model": WAN22_MODEL_NAME,
            "seed": normalized["seed"],
            "fps": normalized["options"]["fps"],
            "duration_sec": normalized["duration_sec"],
            "num_frames": normalized["num_frames"],
            "width": normalized["width"],
            "height": normalized["height"],
            "warnings": warnings,
        }

        return {
            "workflow": workflow,
            "images": images,
            "remote_images": remote_images,
            "meta": meta,
        }, None
    except RuntimeError as exc:
        return None, _error("UNSUPPORTED_REFERENCE_COMBINATION", str(exc))
    except ValueError as exc:
        return None, _error("VALIDATION_ERROR", str(exc))
    except Exception as exc:
        return None, _error("VALIDATION_ERROR", str(exc))
```

- [ ] **Step 6: Run validation and workflow injection tests**

Run:

```bash
python -m unittest tests.test_handler.TestRunpodWorkerComfy \
  -k "t2v or i2v or r2v or legacy" -v
```

If `unittest -k` is unavailable in the local Python version, run:

```bash
python -m unittest tests.test_handler.TestRunpodWorkerComfy.test_valid_t2v_input_builds_wan22_t2v_workflow \
  tests.test_handler.TestRunpodWorkerComfy.test_valid_json_string_input_for_t2v \
  tests.test_handler.TestRunpodWorkerComfy.test_t2v_generate_audio_adds_warning \
  tests.test_handler.TestRunpodWorkerComfy.test_valid_i2v_requires_and_wires_start_frame \
  tests.test_handler.TestRunpodWorkerComfy.test_i2v_missing_start_frame_fails \
  tests.test_handler.TestRunpodWorkerComfy.test_valid_r2v_wires_start_and_end_frames \
  tests.test_handler.TestRunpodWorkerComfy.test_r2v_accepts_first_two_image_urls \
  tests.test_handler.TestRunpodWorkerComfy.test_r2v_missing_second_frame_fails \
  tests.test_handler.TestRunpodWorkerComfy.test_r2v_image_placeholder_requires_matching_image_url \
  tests.test_handler.TestRunpodWorkerComfy.test_r2v_video_placeholder_is_unsupported \
  tests.test_handler.TestRunpodWorkerComfy.test_legacy_image_modes_are_not_supported -v
```

Expected: all listed tests pass.

- [ ] **Step 7: Commit**

```bash
git add handler.py tests/test_handler.py
git commit -m "feat: add Wan2.2 video request validation"
```

---

### Task 5: Implement Remote Asset Fetching and Upload

**Files:**
- Modify: `handler.py`
- Modify: `tests/test_handler.py`

- [ ] **Step 1: Add tests for remote image fetching**

Add these tests to `TestRunpodWorkerComfy`:

```python
    @patch("handler.requests.get")
    def test_fetch_remote_image_as_upload_object(self, mock_get):
        response = MagicMock()
        response.content = b"image-bytes"
        response.headers = {"content-type": "image/png"}
        response.raise_for_status.return_value = None
        mock_get.return_value = response

        result = handler._fetch_remote_image(
            {"name": "start_frame.png", "url": "https://example.com/start.png"}
        )

        self.assertEqual(result["name"], "start_frame.png")
        self.assertEqual(result["image"], base64.b64encode(b"image-bytes").decode("utf-8"))
        mock_get.assert_called_with("https://example.com/start.png", timeout=60)

    @patch("handler.requests.get")
    def test_fetch_remote_image_rejects_non_image_content(self, mock_get):
        response = MagicMock()
        response.content = b"not-image"
        response.headers = {"content-type": "text/plain"}
        response.raise_for_status.return_value = None
        mock_get.return_value = response

        with self.assertRaises(ValueError) as ctx:
            handler._fetch_remote_image(
                {"name": "start_frame.png", "url": "https://example.com/start.txt"}
            )

        self.assertIn("did not return an image", str(ctx.exception))
```

- [ ] **Step 2: Add `_fetch_remote_image`**

Add:

```python
def _fetch_remote_image(remote_image):
    url = remote_image["url"]
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if not content_type.startswith("image/"):
        raise ValueError(f"Remote asset {url} did not return an image content type")
    encoded = base64.b64encode(response.content).decode("utf-8")
    return {"name": remote_image["name"], "image": encoded}
```

- [ ] **Step 3: Modify handler input upload section**

In `handler(job)`, after:

```python
    input_images = validated_data.get("images")
```

add:

```python
    remote_images = validated_data.get("remote_images") or []
    if remote_images:
        try:
            fetched_images = [_fetch_remote_image(item) for item in remote_images]
        except Exception as exc:
            return {
                "error": {
                    "code": "ASSET_FETCH_FAILED",
                    "message": str(exc),
                }
            }
        input_images = (input_images or []) + fetched_images
```

- [ ] **Step 4: Run remote asset tests**

Run:

```bash
python -m unittest tests.test_handler.TestRunpodWorkerComfy.test_fetch_remote_image_as_upload_object \
  tests.test_handler.TestRunpodWorkerComfy.test_fetch_remote_image_rejects_non_image_content -v
```

Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add handler.py tests/test_handler.py
git commit -m "feat: fetch remote video input frames"
```

---

### Task 6: Implement Video Output Collection and S3 Upload

**Files:**
- Modify: `handler.py`
- Modify: `tests/test_handler.py`

- [ ] **Step 1: Add tests for video output collection**

Add:

```python
    @patch("handler.get_image_data", return_value=b"video-bytes")
    @patch("handler._upload_artifact_to_s3", return_value="https://bucket.example.com/out.mp4")
    def test_collect_video_outputs_from_history_videos(self, mock_upload, mock_get):
        history_outputs = {
            "58": {
                "videos": [
                    {
                        "filename": "out.mp4",
                        "subfolder": "video",
                        "type": "output",
                    }
                ]
            }
        }

        videos, errors = handler._collect_video_outputs("job-1", history_outputs)

        self.assertEqual(errors, [])
        self.assertEqual(
            videos,
            [
                {
                    "filename": "out.mp4",
                    "type": "s3_url",
                    "data": "https://bucket.example.com/out.mp4",
                }
            ],
        )
        mock_get.assert_called_with("out.mp4", "video", "output")
        self.assertTrue(mock_upload.called)

    @patch("handler.get_image_data", return_value=b"video-bytes")
    @patch("handler._upload_artifact_to_s3", return_value="https://bucket.example.com/out.mp4")
    def test_collect_video_outputs_from_history_gifs(self, mock_upload, mock_get):
        history_outputs = {
            "58": {
                "gifs": [
                    {
                        "filename": "out.mp4",
                        "subfolder": "video",
                        "type": "output",
                    }
                ]
            }
        }

        videos, errors = handler._collect_video_outputs("job-1", history_outputs)

        self.assertEqual(errors, [])
        self.assertEqual(videos[0]["filename"], "out.mp4")
```

- [ ] **Step 2: Add S3 configuration helper and artifact upload**

Add:

```python
def _require_s3_config():
    if not os.environ.get("BUCKET_ENDPOINT_URL"):
        raise ValueError("S3 artifact upload is required for video deployment")


def _upload_artifact_to_s3(job_id, filename, artifact_bytes):
    _require_s3_config()
    suffix = os.path.splitext(filename)[1] or ".mp4"
    temp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
            temp_file.write(artifact_bytes)
            temp_file_path = temp_file.name
        return rp_upload.upload_image(job_id, temp_file_path)
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
```

- [ ] **Step 3: Add video output collector**

Add:

```python
def _collect_video_outputs(job_id, outputs):
    videos = []
    errors = []
    for node_id, node_output in outputs.items():
        video_items = []
        for key in ("videos", "gifs"):
            video_items.extend(node_output.get(key, []))

        for video_info in video_items:
            filename = video_info.get("filename")
            subfolder = video_info.get("subfolder", "")
            output_type = video_info.get("type")
            if not filename:
                errors.append(f"Skipping video in node {node_id} due to missing filename")
                continue

            video_bytes = get_image_data(filename, subfolder, output_type)
            if not video_bytes:
                errors.append(f"Failed to fetch video data for {filename} from /view endpoint")
                continue

            try:
                s3_url = _upload_artifact_to_s3(job_id, filename, video_bytes)
            except Exception as exc:
                errors.append(f"Error uploading {filename} to S3: {exc}")
                continue

            videos.append({"filename": filename, "type": "s3_url", "data": s3_url})
    return videos, errors
```

- [ ] **Step 4: Replace image output processing in `handler(job)`**

In `handler(job)`, replace the `output_data = []` variable with:

```python
    output_videos = []
```

After history `outputs` is extracted, replace the existing image-processing loop with:

```python
        output_videos, output_errors = _collect_video_outputs(job_id, outputs)
        errors.extend(output_errors)
```

Replace final result assembly with:

```python
    final_result = {
        "videos": output_videos,
        "meta": validated_data.get("meta", {}),
    }

    if errors:
        final_result["errors"] = errors
        final_result["meta"].setdefault("warnings", [])
        final_result["meta"]["warnings"].extend(errors)
        print(f"worker-comfyui - Job completed with errors/warnings: {errors}")

    if not output_videos:
        print("worker-comfyui - Job failed with no output videos.")
        return {
            "error": {
                "code": "OUTPUT_NOT_FOUND",
                "message": "Job processing failed with no output videos",
                "details": errors,
            }
        }

    print(f"worker-comfyui - Job completed. Returning {len(output_videos)} video(s).")
    return final_result
```

- [ ] **Step 5: Update upload image failure shape**

In the input image upload failure branch, return structured errors:

```python
            return {
                "error": {
                    "code": "ASSET_UPLOAD_FAILED",
                    "message": "Failed to upload one or more input images",
                    "details": upload_result["details"],
                }
            }
```

- [ ] **Step 6: Run output collection tests**

Run:

```bash
python -m unittest tests.test_handler.TestRunpodWorkerComfy.test_collect_video_outputs_from_history_videos \
  tests.test_handler.TestRunpodWorkerComfy.test_collect_video_outputs_from_history_gifs -v
```

Expected: both tests pass.

- [ ] **Step 7: Commit**

```bash
git add handler.py tests/test_handler.py
git commit -m "feat: return Wan2.2 video artifacts"
```

---

### Task 7: Add Production Wan2.2 Workflows

**Files:**
- Create: `workflows/wan2_2_14b_t2v.json`
- Create: `workflows/wan2_2_14b_i2v.json`
- Create: `workflows/wan2_2_14b_flf2v.json`

- [ ] **Step 1: Create the three production workflow files**

Use official ComfyUI Wan2.2 native workflows exported in API format. The source UI templates are:

```text
https://raw.githubusercontent.com/Comfy-Org/workflow_templates/refs/heads/main/templates/video_wan2_2_14B_t2v.json
https://raw.githubusercontent.com/Comfy-Org/workflow_templates/refs/heads/main/templates/video_wan2_2_14B_i2v.json
https://raw.githubusercontent.com/Comfy-Org/workflow_templates/refs/heads/main/templates/video_wan2_2_14B_flf2v.json
```

Load each source workflow into a matching ComfyUI build and export it with "Save (API Format)" so each file is a prompt dictionary keyed by node id with `class_type` and `inputs`. The saved files must look like this shape:

```json
{
  "6": {
    "class_type": "CLIPTextEncode",
    "inputs": {
      "text": "prompt text",
      "clip": ["38", 0]
    },
    "_meta": {
      "title": "CLIP Text Encode (Positive Prompt)"
    }
  }
}
```

Do not commit the raw UI workflow format with top-level `nodes` and `links`; `/prompt` will not accept that format.

- [ ] **Step 2: Verify production workflow JSON is API format**

Run:

```bash
python - <<'PY'
import json
from pathlib import Path

for path in [
    Path("workflows/wan2_2_14b_t2v.json"),
    Path("workflows/wan2_2_14b_i2v.json"),
    Path("workflows/wan2_2_14b_flf2v.json"),
]:
    data = json.loads(path.read_text())
    assert isinstance(data, dict), path
    assert "nodes" not in data, f"{path} is UI workflow format"
    assert all("class_type" in node and "inputs" in node for node in data.values()), path
    print(f"OK {path}")
PY
```

Expected:

```text
OK workflows/wan2_2_14b_t2v.json
OK workflows/wan2_2_14b_i2v.json
OK workflows/wan2_2_14b_flf2v.json
```

- [ ] **Step 3: Verify injection finds required nodes**

Run:

```bash
python - <<'PY'
import handler

for mode in ["t2v", "i2v", "r2v"]:
    payload = {"mode": mode, "prompt": "test video"}
    if mode == "i2v":
        payload["start_frame"] = "data:image/png;base64,ZmFrZQ=="
    if mode == "r2v":
        payload["start_frame"] = "data:image/png;base64,c3RhcnQ="
        payload["end_frame"] = "data:image/png;base64,ZW5k"
    data, error = handler.validate_input(payload)
    assert error is None, error
    workflow = data["workflow"]
    assert any(node.get("class_type") == "SaveVideo" for node in workflow.values())
    print(mode, data["meta"])
PY
```

Expected: all three modes print metadata without assertion errors.

- [ ] **Step 4: Commit**

```bash
git add workflows/wan2_2_14b_t2v.json workflows/wan2_2_14b_i2v.json workflows/wan2_2_14b_flf2v.json
git commit -m "feat: add Wan2.2 14B video workflows"
```

---

### Task 8: Add Wan2.2 Docker Model Target

**Files:**
- Modify: `Dockerfile`
- Modify: `docker-bake.hcl`
- Test: `tests/test_dockerfile.py`

- [ ] **Step 1: Update Dockerfile model directories**

In the downloader stage `mkdir -p` line, ensure these directories are present:

```dockerfile
RUN mkdir -p models/checkpoints models/vae models/unet models/clip models/text_encoders models/diffusion_models models/model_patches models/loras models/audio_encoders models/upscale_models
```

- [ ] **Step 2: Add `MODEL_TYPE=wan2.2-14b` downloads**

Add after the existing `flux2-dev` block:

```dockerfile
RUN if [ "$MODEL_TYPE" = "wan2.2-14b" ]; then \
      wget -q -O models/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors && \
      wget -q -O models/diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors && \
      wget -q -O models/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors && \
      wget -q -O models/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors && \
      wget -q -O models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors && \
      wget -q -O models/vae/wan_2.1_vae.safetensors https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors; \
    fi
```

- [ ] **Step 3: Add docker bake target**

In `docker-bake.hcl`, add `wan2.2-14b` to the default targets list and add:

```hcl
target "wan2.2-14b" {
  inherits = ["docker-metadata-action"]
  context = "."
  dockerfile = "Dockerfile"
  platforms = ["linux/amd64"]
  args = {
    MODEL_TYPE = "wan2.2-14b"
  }
  tags = ["${DOCKERHUB_REPO}/${DOCKERHUB_IMG}:${RELEASE_VERSION}-wan2.2-14b"]
}
```

- [ ] **Step 4: Add Dockerfile tests**

In `tests/test_dockerfile.py`, add:

```python
    def test_wan22_model_type_downloads_required_models(self):
        self.assertIn('MODEL_TYPE" = "wan2.2-14b"', self.dockerfile)
        self.assertIn("wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors", self.dockerfile)
        self.assertIn("wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors", self.dockerfile)
        self.assertIn("wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors", self.dockerfile)
        self.assertIn("wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors", self.dockerfile)
        self.assertIn("umt5_xxl_fp8_e4m3fn_scaled.safetensors", self.dockerfile)
        self.assertIn("wan_2.1_vae.safetensors", self.dockerfile)
```

- [ ] **Step 5: Run Dockerfile tests**

Run:

```bash
python -m unittest tests.test_dockerfile -v
```

Expected: all Dockerfile tests pass.

- [ ] **Step 6: Commit**

```bash
git add Dockerfile docker-bake.hcl tests/test_dockerfile.py
git commit -m "feat: add Wan2.2 14B docker target"
```

---

### Task 9: Update Docs and Sample Input

**Files:**
- Modify: `README.md`
- Modify: `docs/configuration.md`
- Modify: `test_input.json`

- [ ] **Step 1: Update `test_input.json`**

Replace with:

```json
{
  "input": {
    "mode": "t2v",
    "prompt": "A cinematic shot of a red aircraft crossing a stormy sky, smooth camera motion",
    "negative_prompt": "low quality, blur, distorted",
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

- [ ] **Step 2: Update README API section**

Replace the current image `Input` and `Output` sections with video-only examples:

````markdown
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

- `t2v`: text-to-video using Wan2.2 14B T2V.
- `i2v`: image-to-video using Wan2.2 14B I2V. Requires `start_frame`.
- `r2v`: first-last-frame video using Wan2.2 14B FLF2V. Requires `start_frame` and `end_frame`, or `image_urls[0]` and `image_urls[1]`.

Wan2.2 T2V/I2V/FLF2V outputs silent videos. `generate_audio=true` is accepted but returns `AUDIO_NOT_SUPPORTED_BY_WORKFLOW` in `meta.warnings`.
````

Add output example:

````markdown
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
  }
}
```
````

- [ ] **Step 3: Update `docs/configuration.md`**

Add rows:

```markdown
| `WAN22_T2V_WORKFLOW_PATH` | Override path for the Wan2.2 14B T2V API-format workflow. | `/workflows/wan2_2_14b_t2v.json` |
| `WAN22_I2V_WORKFLOW_PATH` | Override path for the Wan2.2 14B I2V API-format workflow. | `/workflows/wan2_2_14b_i2v.json` |
| `WAN22_R2V_WORKFLOW_PATH` | Override path for the Wan2.2 14B FLF2V API-format workflow. | `/workflows/wan2_2_14b_flf2v.json` |
```

Add this note to the S3 section:

```markdown
Wan2.2 video deployments require S3-compatible upload configuration. Video artifacts are not returned inline as base64 in production.
```

- [ ] **Step 4: Verify docs do not advertise image modes**

Run:

```bash
rg -n "t2i|i2i|output\\.images|Flux2" README.md docs/configuration.md test_input.json
```

Expected: no matches in the updated video-only API sections. If matches remain in unrelated historical docs, keep them only when the text explicitly says they apply to older image deployments.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/configuration.md test_input.json
git commit -m "docs: document Wan2.2 video worker API"
```

---

### Task 10: Full Verification

**Files:**
- No file edits unless verification exposes a bug.

- [ ] **Step 1: Run unit tests**

Run:

```bash
python -m unittest tests.test_handler tests.test_dockerfile tests.test_start_sh -v
```

Expected: all tests pass.

- [ ] **Step 2: Run JSON validation**

Run:

```bash
python -m json.tool test_input.json >/dev/null
python -m json.tool workflows/wan2_2_14b_t2v.json >/dev/null
python -m json.tool workflows/wan2_2_14b_i2v.json >/dev/null
python -m json.tool workflows/wan2_2_14b_flf2v.json >/dev/null
```

Expected: all commands exit `0`.

- [ ] **Step 3: Run handler validation smoke test**

Run:

```bash
python - <<'PY'
import json
import handler

with open("test_input.json", "r", encoding="utf-8") as f:
    payload = json.load(f)["input"]

validated, error = handler.validate_input(payload)
assert error is None, error
assert validated["meta"]["mode"] == "t2v"
assert validated["meta"]["model"] == "wan2.2-14b"
assert validated["meta"]["num_frames"] == 120
print(validated["meta"])
PY
```

Expected: prints T2V metadata.

- [ ] **Step 4: Build syntax-only Docker target check**

Run:

```bash
docker build --platform linux/amd64 --build-arg MODEL_TYPE=none -t worker-comfyui:wan22-plan-check .
```

Expected: build completes. This does not download Wan2.2 models.

- [ ] **Step 5: Record full Wan2.2 build command for deployment**

Do not run this command during normal unit verification because it downloads large model files:

```bash
docker build --platform linux/amd64 --build-arg MODEL_TYPE=wan2.2-14b -t worker-comfyui:wan2.2-14b .
```

- [ ] **Step 6: Final commit if verification fixes were needed**

If verification required code or docs changes:

```bash
git add handler.py tests/test_handler.py tests/test_dockerfile.py README.md docs/configuration.md test_input.json workflows/wan2_2_14b_t2v.json workflows/wan2_2_14b_i2v.json workflows/wan2_2_14b_flf2v.json
git commit -m "fix: complete Wan2.2 video worker verification"
```

If no changes were needed, do not create an empty commit.

---

## Self-Review Notes

- Spec coverage: The plan covers video-only mode support, Wan2.2 workflow files, `r2v` as FLF2V, silent video warning for `generate_audio`, S3 video artifacts, Docker model target, docs, and tests.
- Scope: Wan2.2 S2V and custom `/v1/videos/*` routes remain out of scope.
- API workflow risk: official ComfyUI template downloads are UI workflow JSON. Task 7 explicitly requires API-format exports before committing production workflow files.
