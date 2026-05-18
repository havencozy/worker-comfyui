import runpod
from runpod.serverless.utils import rp_upload
import json
import urllib.request
import urllib.parse
import time
import os
import requests
import base64
from io import BytesIO
import websocket
import uuid
import tempfile
import socket
import traceback
import logging
import copy

from network_volume import (
    is_network_volume_debug_enabled,
    run_network_volume_diagnostics,
)

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Time to wait between API check attempts in milliseconds
COMFY_API_AVAILABLE_INTERVAL_MS = int(
    os.environ.get("COMFY_API_AVAILABLE_INTERVAL_MS", 50)
)
# Maximum number of API check attempts (0 = no limit, poll while ComfyUI process is alive)
COMFY_API_AVAILABLE_MAX_RETRIES = int(
    os.environ.get("COMFY_API_AVAILABLE_MAX_RETRIES", 0)
)
# Fallback retry limit when PID file is unavailable and retries=0
COMFY_API_FALLBACK_MAX_RETRIES = 500
# PID file written by start.sh so we can detect if ComfyUI has crashed
COMFY_PID_FILE = "/tmp/comfyui.pid"
# Websocket reconnection behaviour (can be overridden through environment variables)
# NOTE: more attempts and diagnostics improve debuggability whenever ComfyUI crashes mid-job.
#   • WEBSOCKET_RECONNECT_ATTEMPTS sets how many times we will try to reconnect.
#   • WEBSOCKET_RECONNECT_DELAY_S sets the sleep in seconds between attempts.
#
# If the respective env-vars are not supplied we fall back to sensible defaults ("5" and "3").
WEBSOCKET_RECONNECT_ATTEMPTS = int(os.environ.get("WEBSOCKET_RECONNECT_ATTEMPTS", 5))
WEBSOCKET_RECONNECT_DELAY_S = int(os.environ.get("WEBSOCKET_RECONNECT_DELAY_S", 3))

# Extra verbose websocket trace logs (set WEBSOCKET_TRACE=true to enable)
if os.environ.get("WEBSOCKET_TRACE", "false").lower() == "true":
    # This prints low-level frame information to stdout which is invaluable for diagnosing
    # protocol errors but can be noisy in production – therefore gated behind an env-var.
    websocket.enableTrace(True)

# Host where ComfyUI is running
COMFY_HOST = "127.0.0.1:8188"
# Enforce a clean state after each job is done
# see https://docs.runpod.io/docs/handler-additional-controls#refresh-worker
REFRESH_WORKER = os.environ.get("REFRESH_WORKER", "false").lower() == "true"

WORKFLOW_DIR = os.environ.get(
    "WORKFLOW_DIR", os.path.join(os.path.dirname(__file__), "workflows")
)

WAN22_MODEL_NAME = "wan2.2-14b"
VIDEO_MODES = {"t2v", "i2v", "r2v"}
VIDEO_MODE_ALIASES = {
    "wan22-t2v": "t2v",
    "wan22-i2v": "i2v",
    "wan22-flf2v": "r2v",
}
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
VIDEO_OUTPUT_EXTENSIONS = (".mp4", ".webm", ".mkv", ".mov", ".avi", ".gif")
HISTORY_VIDEO_KEYS = ("videos", "gifs", "animated")
WAN22_REQUIRED_MODEL_FILES = (
    "diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors",
    "diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors",
    "diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
    "diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
    "text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
    "vae/wan_2.1_vae.safetensors",
)


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

# Built-in custom API workflow templates (override via env if needed)
FLUX2_T2I_WORKFLOW_PATH = os.environ.get(
    "FLUX2_T2I_WORKFLOW_PATH", os.path.join(WORKFLOW_DIR, "flux2_t2i.json")
)
FLUX2_I2I_WORKFLOW_PATH = os.environ.get(
    "FLUX2_I2I_WORKFLOW_PATH", os.path.join(WORKFLOW_DIR, "flux2_i2i.json")
)

ASPECT_RATIO_PRESETS = {
    "1:1": (1024, 1024),
    "16:9": (1344, 768),
    "9:16": (768, 1344),
    "4:3": (1152, 896),
    "3:4": (896, 1152),
    "3:2": (1216, 832),
    "2:3": (832, 1216),
}

# Presets for quickly switching Flux model assets without changing workflow files.
# You can override/extend this map via FLUX_MODEL_PRESETS_JSON env var.
DEFAULT_FLUX_MODEL_PRESETS = {
    "flux2-dev": {
        "unet_name": "flux2_dev_fp8mixed.safetensors",
        "clip_name": "mistral_3_small_flux2_bf16.safetensors",
        "vae_name": "flux2-vae.safetensors",
    },
    "flux2-schnell": {
        "unet_name": "flux2_schnell_fp8mixed.safetensors",
        "clip_name": "mistral_3_small_flux2_bf16.safetensors",
        "vae_name": "flux2-vae.safetensors",
    },
}

# Runtime download manifest (used by API call preflight: check model -> download if missing)
# Extend/override with FLUX_MODEL_ASSETS_JSON env.
DEFAULT_FLUX_MODEL_ASSETS = {
    "flux2-dev": [
        {
            "path": "models/clip/mistral_3_small_flux2_bf16.safetensors", 
            "url": "https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/text_encoders/mistral_3_small_flux2_bf16.safetensors",
        },
        {
            "path": "models/unet/flux2_dev_fp8mixed.safetensors",
            "url": "https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/diffusion_models/flux2_dev_fp8mixed.safetensors",
        },
        {
            "path": "models/vae/flux2-vae.safetensors",
            "url": "https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/vae/flux2-vae.safetensors",
        }
    ]
}

# ---------------------------------------------------------------------------
# Helper: quick reachability probe of ComfyUI HTTP endpoint (port 8188)
# ---------------------------------------------------------------------------


def _comfy_server_status():
    """Return a dictionary with basic reachability info for the ComfyUI HTTP server."""
    try:
        resp = requests.get(f"http://{COMFY_HOST}/", timeout=5)
        return {
            "reachable": resp.status_code == 200,
            "status_code": resp.status_code,
        }
    except Exception as exc:
        return {"reachable": False, "error": str(exc)}


def _attempt_websocket_reconnect(ws_url, max_attempts, delay_s, initial_error):
    """
    Attempts to reconnect to the WebSocket server after a disconnect.

    Args:
        ws_url (str): The WebSocket URL (including client_id).
        max_attempts (int): Maximum number of reconnection attempts.
        delay_s (int): Delay in seconds between attempts.
        initial_error (Exception): The error that triggered the reconnect attempt.

    Returns:
        websocket.WebSocket: The newly connected WebSocket object.

    Raises:
        websocket.WebSocketConnectionClosedException: If reconnection fails after all attempts.
    """
    print(
        f"worker-comfyui - Websocket connection closed unexpectedly: {initial_error}. Attempting to reconnect..."
    )
    last_reconnect_error = initial_error
    for attempt in range(max_attempts):
        # Log current server status before each reconnect attempt so that we can
        # see whether ComfyUI is still alive (HTTP port 8188 responding) even if
        # the websocket dropped. This is extremely useful to differentiate
        # between a network glitch and an outright ComfyUI crash/OOM-kill.
        srv_status = _comfy_server_status()
        if not srv_status["reachable"]:
            # If ComfyUI itself is down there is no point in retrying the websocket –
            # bail out immediately so the caller gets a clear "ComfyUI crashed" error.
            print(
                f"worker-comfyui - ComfyUI HTTP unreachable – aborting websocket reconnect: {srv_status.get('error', 'status '+str(srv_status.get('status_code')))}"
            )
            raise websocket.WebSocketConnectionClosedException(
                "ComfyUI HTTP unreachable during websocket reconnect"
            )

        # Otherwise we proceed with reconnect attempts while server is up
        print(
            f"worker-comfyui - Reconnect attempt {attempt + 1}/{max_attempts}... (ComfyUI HTTP reachable, status {srv_status.get('status_code')})"
        )
        try:
            # Need to create a new socket object for reconnect
            new_ws = websocket.WebSocket()
            new_ws.connect(ws_url, timeout=10)  # Use existing ws_url
            print(f"worker-comfyui - Websocket reconnected successfully.")
            return new_ws  # Return the new connected socket
        except (
            websocket.WebSocketException,
            ConnectionRefusedError,
            socket.timeout,
            OSError,
        ) as reconn_err:
            last_reconnect_error = reconn_err
            print(
                f"worker-comfyui - Reconnect attempt {attempt + 1} failed: {reconn_err}"
            )
            if attempt < max_attempts - 1:
                print(
                    f"worker-comfyui - Waiting {delay_s} seconds before next attempt..."
                )
                time.sleep(delay_s)
            else:
                print(f"worker-comfyui - Max reconnection attempts reached.")

    # If loop completes without returning, raise an exception
    print("worker-comfyui - Failed to reconnect websocket after connection closed.")
    raise websocket.WebSocketConnectionClosedException(
        f"Connection closed and failed to reconnect. Last error: {last_reconnect_error}"
    )


def validate_input(job_input):
    """
    Validates the input for the handler function.

    Args:
        job_input (dict): The input data to validate.

    Returns:
        tuple: A tuple containing the validated data and an error message, if any.
               The structure is (validated_data, error_message).
    """
    # Validate if job_input is provided
    if job_input is None:
        return None, _error("VALIDATION_ERROR", "Please provide input")

    # Check if input is a string and try to parse it as JSON
    if isinstance(job_input, str):
        try:
            job_input = json.loads(job_input)
        except json.JSONDecodeError:
            return None, _error("VALIDATION_ERROR", "Invalid JSON format in input")

    if not isinstance(job_input, dict):
        return None, _error("VALIDATION_ERROR", "Input must be an object")

    raw_mode = job_input.get("mode")
    mode = VIDEO_MODE_ALIASES.get(raw_mode, raw_mode)
    if mode in VIDEO_MODES:
        normalized_job_input = _normalize_video_mode_payload(job_input, mode)
        return _build_video_mode_input(normalized_job_input, mode)

    if mode in {"t2i", "i2i"}:
        return None, _error(
            "UNSUPPORTED_MODE",
            "This deployment supports video modes only: 't2v', 'i2v', 'r2v'",
        )

    return None, _error(
        "UNSUPPORTED_MODE",
        "Missing or invalid 'mode'. Supported values: 't2v', 'i2v', 'r2v', "
        "'wan22-t2v', 'wan22-i2v', 'wan22-flf2v'",
    )


def _load_workflow_template(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Accept either raw workflow or wrapped {"input":{"workflow":...}}
    if isinstance(data, dict) and "input" in data and "workflow" in data["input"]:
        return copy.deepcopy(data["input"]["workflow"])

    return copy.deepcopy(data)


def _error(code, message):
    return {"code": code, "message": message}


def _normalize_video_mode_payload(job_input, mode):
    normalized = dict(job_input)
    normalized["mode"] = mode

    if mode in {"i2v", "r2v"} and normalized.get("image") and not normalized.get(
        "start_frame"
    ):
        normalized["start_frame"] = normalized["image"]

    if mode == "r2v":
        for alias in ("end_image", "last_image"):
            if normalized.get(alias) and not normalized.get("end_frame"):
                normalized["end_frame"] = normalized[alias]
                break

    return normalized


def _wan22_model_roots():
    raw_roots = os.environ.get("WAN22_MODEL_ROOTS")
    if raw_roots:
        candidates = [root for root in raw_roots.split(os.pathsep) if root]
    else:
        comfy_root = os.environ.get("COMFY_ROOT", "/comfyui")
        candidates = [
            "/runpod-volume/models",
            os.path.join(comfy_root, "models"),
            "/comfyui/models",
        ]

    roots = []
    for root in candidates:
        normalized = os.path.normpath(root)
        if normalized not in roots:
            roots.append(normalized)
    return roots


def _check_wan22_model_assets():
    roots = _wan22_model_roots()
    missing = []

    for rel_path in WAN22_REQUIRED_MODEL_FILES:
        if any(os.path.exists(os.path.join(root, rel_path)) for root in roots):
            continue
        missing.append(f"models/{rel_path}")

    if not missing:
        return True, None

    return False, {
        "code": "MODEL_ASSET_MISSING",
        "message": (
            "Missing Wan2.2 model files: "
            + ", ".join(missing)
            + ". Expected them under one of: "
            + ", ".join(roots)
        ),
    }


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
    length = raw_options.get("length")
    if length is not None:
        length = int(length)

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
    if length is not None and (length < 1 or length > 450):
        raise ValueError("'options.length' must be between 1 and 450 frames")

    normalized = {
        "fps": fps,
        "steps": steps,
        "guidance_scale": guidance_scale,
        "motion_strength": motion_strength,
        "strength": strength,
    }
    if length is not None:
        normalized["length"] = length
    return normalized


def _normalize_seed(job_input):
    raw_options = job_input.get("options") or {}
    seed_value = job_input.get("seed")
    if seed_value is None and isinstance(raw_options, dict):
        seed_value = raw_options.get("seed")

    if seed_value is None:
        return int(time.time_ns() % 2147483647)
    seed = int(seed_value)
    if seed < 0 or seed > 2147483647:
        raise ValueError("'seed' must be between 0 and 2147483647")
    return seed


def _validate_video_request(job_input, mode):
    prompt = _require_prompt(job_input)
    options = _normalize_video_options(job_input)
    width, height = _resolve_video_dimensions(
        job_input.get("resolution", "720p"),
        job_input.get("aspect_ratio", "auto"),
    )
    duration_sec = _resolve_duration_sec(job_input.get("duration", "auto"))
    if options.get("length") is not None:
        num_frames = options["length"]
        duration_sec = round(num_frames / options["fps"], 3)
    else:
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


def _video_workflow_path(mode):
    if mode == "t2v":
        return WAN22_T2V_WORKFLOW_PATH
    if mode == "i2v":
        return WAN22_I2V_WORKFLOW_PATH
    if mode == "r2v":
        return WAN22_R2V_WORKFLOW_PATH
    raise ValueError(f"Unsupported video mode '{mode}'")


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
            raise ValueError(
                f"Prompt references @Image{marker}, but image_urls[{marker - 1}] is missing"
            )

    for marker in _extract_placeholders(prompt, "Video"):
        raise RuntimeError(
            f"@Video{marker} references are not supported by this Wan2.2 FLF2V deployment"
        )

    for marker in _extract_placeholders(prompt, "Audio"):
        raise RuntimeError(
            f"@Audio{marker} references are not supported by this Wan2.2 FLF2V deployment"
        )


def _frame_assets_for_mode(job_input, mode, prompt):
    _validate_reference_placeholders(job_input, prompt)
    start_frame_name = job_input.get("image_name") or "start_frame.png"
    end_frame_name = job_input.get("end_image_name") or "end_frame.png"

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
        return [{"name": start_frame_name, "image": start_frame}], [], warnings

    start_frame = job_input.get("start_frame")
    end_frame = job_input.get("end_frame")
    if start_frame and end_frame:
        return [
            {"name": start_frame_name, "image": start_frame},
            {"name": end_frame_name, "image": end_frame},
        ], [], []

    image_urls = job_input.get("image_urls") or []
    if len(image_urls) >= 2:
        return [], [
            {"name": start_frame_name, "url": image_urls[0]},
            {"name": end_frame_name, "url": image_urls[1]},
        ], []

    raise ValueError(
        "r2v mode requires two frame references via start_frame/end_frame or image_urls[0]/image_urls[1]"
    )


def _set_video_dimensions_and_length(workflow, width, height, num_frames):
    for node in workflow.values():
        inputs = node.get("inputs", {})
        class_type = node.get("class_type", "")
        if class_type in {
            "EmptyHunyuanLatentVideo",
            "WanImageToVideo",
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


def _video_filename_prefix(mode, job_id=None):
    if job_id:
        return f"video/{job_id}_wan22_{mode}"
    return f"video/wan22_{mode}"


def _set_video_save_fields(workflow, mode, fps, job_id=None):
    for node in workflow.values():
        inputs = node.get("inputs", {})
        class_type = node.get("class_type", "")
        if class_type == "SaveVideo":
            if "filename_prefix" in inputs:
                inputs["filename_prefix"] = _video_filename_prefix(mode, job_id)
            if "fps" in inputs:
                inputs["fps"] = int(fps)
        if class_type == "CreateVideo" and "fps" in inputs:
            inputs["fps"] = int(fps)


def _set_video_load_image_fields(
    workflow, mode, start_frame_name="start_frame.png", end_frame_name="end_frame.png"
):
    load_images = [
        (node_id, node)
        for node_id, node in workflow.items()
        if node.get("class_type") == "LoadImage"
    ]
    if mode == "i2v" and load_images:
        load_images[0][1].setdefault("inputs", {})["image"] = start_frame_name
        return
    if mode == "r2v":
        for node_id, node in load_images:
            title = ((node.get("_meta") or {}).get("title", "")).lower()
            if "end" in title or "last" in title:
                node.setdefault("inputs", {})["image"] = end_frame_name
            else:
                node.setdefault("inputs", {})["image"] = start_frame_name


def _build_video_mode_input(job_input, mode):
    try:
        normalized = _validate_video_request(job_input, mode)
        images, remote_images, asset_warnings = _frame_assets_for_mode(
            job_input, mode, normalized["prompt"]
        )
        workflow = _load_workflow_template(_video_workflow_path(mode))
        start_frame_name = job_input.get("image_name") or "start_frame.png"
        end_frame_name = job_input.get("end_image_name") or "end_frame.png"

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
        _set_video_load_image_fields(
            workflow,
            mode,
            start_frame_name=start_frame_name,
            end_frame_name=end_frame_name,
        )

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


def _fetch_remote_image(remote_image):
    url = remote_image["url"]
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if not content_type.startswith("image/"):
        raise ValueError(f"Remote asset {url} did not return an image content type")
    encoded = base64.b64encode(response.content).decode("utf-8")
    return {"name": remote_image["name"], "image": encoded}


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


def _history_value_key_summary(value, depth=0):
    if isinstance(value, dict):
        keys = sorted(str(key) for key in value.keys())
        summary = {"type": "dict", "keys": keys}
        media_fields = {}
        for field in ("filename", "subfolder", "type", "format"):
            if field in value:
                media_fields[field] = value[field]
        if media_fields:
            summary["media_fields"] = media_fields
        if depth < 4:
            summary["children"] = {
                str(key): _history_value_key_summary(child, depth + 1)
                for key, child in value.items()
            }
        return summary

    if isinstance(value, list):
        item_summaries = [
            _history_value_key_summary(item, depth + 1) for item in value
        ]
        return {
            "type": "list",
            "count": len(value),
            "items": item_summaries,
        }

    return {"type": type(value).__name__}


def _history_outputs_key_summary(outputs):
    return {
        str(node_id): _history_value_key_summary(node_output)
        for node_id, node_output in (outputs or {}).items()
    }


def _collect_video_outputs(job_id, outputs):
    videos = []
    errors = []
    print(
        "worker-comfyui - Full history output key summary: "
        + json.dumps(
            _history_outputs_key_summary(outputs),
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    for node_id, node_output in outputs.items():
        node_output = node_output or {}
        video_items = []
        for key in HISTORY_VIDEO_KEYS:
            video_items.extend(node_output.get(key, []))
        for image_info in node_output.get("images", []):
            filename = image_info.get("filename", "")
            if filename.lower().endswith(VIDEO_OUTPUT_EXTENSIONS):
                video_items.append(image_info)

        print(
            "worker-comfyui - History output node "
            f"{node_id}: keys={sorted((node_output or {}).keys())}, "
            f"video_items={len(video_items)}"
        )
        for video_info in video_items:
            filename = video_info.get("filename")
            subfolder = video_info.get("subfolder", "")
            output_type = video_info.get("type")
            print(
                "worker-comfyui - History video candidate: "
                f"node={node_id}, filename={filename}, "
                f"subfolder={subfolder}, type={output_type}"
            )
            if not filename:
                errors.append(
                    f"Skipping video in node {node_id} due to missing filename"
                )
                continue

            video_bytes = get_image_data(filename, subfolder, output_type)
            if not video_bytes:
                errors.append(
                    f"Failed to fetch video data for {filename} from /view endpoint"
                )
                continue

            try:
                s3_url = _upload_artifact_to_s3(job_id, filename, video_bytes)
            except Exception as exc:
                errors.append(f"Error uploading {filename} to S3: {exc}")
                continue

            print(f"worker-comfyui - Uploaded history video artifact: {filename}")
            videos.append({"filename": filename, "type": "s3_url", "data": s3_url})
    return videos, errors


def _comfy_output_dirs():
    explicit_output_dir = os.environ.get("COMFY_OUTPUT_DIR")
    if explicit_output_dir:
        return [explicit_output_dir]

    candidates = ["/comfyui/output"]
    comfy_root = os.environ.get("COMFY_ROOT")
    if comfy_root:
        candidates.append(os.path.join(comfy_root, "output"))

    output_dirs = []
    for output_dir in candidates:
        normalized = os.path.normpath(output_dir)
        if normalized not in output_dirs:
            output_dirs.append(normalized)
    return output_dirs


def _iter_recent_video_paths(output_dir, since_epoch, filename_prefix=None):
    normalized_prefix = None
    search_dir = output_dir
    if filename_prefix:
        normalized_prefix = os.path.normpath(filename_prefix)
        prefix_dir = os.path.dirname(normalized_prefix)
        if prefix_dir:
            search_dir = os.path.join(output_dir, prefix_dir)
        normalized_prefix = os.path.basename(normalized_prefix)

    print(
        "worker-comfyui - Scanning ComfyUI output directory for videos: "
        f"output_dir={output_dir}, search_dir={search_dir}, "
        f"filename_prefix={filename_prefix}, normalized_prefix={normalized_prefix}, "
        f"since_epoch={since_epoch:.3f}"
    )
    if not os.path.isdir(search_dir) and search_dir != output_dir:
        print(
            "worker-comfyui - Video prefix directory does not exist; "
            f"falling back to output directory scan: {search_dir}"
        )
        search_dir = output_dir

    if not os.path.isdir(search_dir):
        print(
            "worker-comfyui - Video output search directory does not exist: "
            f"{search_dir}"
        )
        return []

    matches = []
    skipped_prefix = 0
    skipped_extension = 0
    skipped_old = 0
    scanned_files = 0
    for root, _dirs, files in os.walk(search_dir):
        for filename in files:
            scanned_files += 1
            if normalized_prefix and not filename.startswith(normalized_prefix):
                skipped_prefix += 1
                continue
            if not filename.lower().endswith(VIDEO_OUTPUT_EXTENSIONS):
                skipped_extension += 1
                continue

            path = os.path.join(root, filename)
            try:
                modified_at = os.path.getmtime(path)
            except OSError:
                continue
            if modified_at < since_epoch:
                skipped_old += 1
                continue
            matches.append((modified_at, path))

    matches.sort(reverse=True)
    preview = [
        {
            "path": path,
            "mtime": round(modified_at, 3),
            "size": os.path.getsize(path) if os.path.exists(path) else None,
        }
        for modified_at, path in matches[:5]
    ]
    print(
        "worker-comfyui - Video output scan complete: "
        f"scanned_files={scanned_files}, matches={len(matches)}, "
        f"skipped_prefix={skipped_prefix}, skipped_extension={skipped_extension}, "
        f"skipped_old={skipped_old}, preview={preview}"
    )
    return [path for _modified_at, path in matches]


def _collect_recent_video_files(job_id, since_epoch, filename_prefix=None):
    videos = []
    errors = []
    output_dirs = _comfy_output_dirs()
    print(
        "worker-comfyui - Candidate ComfyUI output directories for video scan: "
        f"{output_dirs}"
    )
    video_paths = []
    scanned_output_dirs = []
    for output_dir in output_dirs:
        scanned_output_dirs.append(output_dir)
        video_paths = _iter_recent_video_paths(
            output_dir, since_epoch, filename_prefix
        )
        if video_paths:
            break

    for path in video_paths:
        filename = os.path.basename(path)
        try:
            with open(path, "rb") as video_file:
                video_bytes = video_file.read()
            print(
                "worker-comfyui - Uploading fallback video artifact from disk: "
                f"path={path}, filename={filename}, bytes={len(video_bytes)}"
            )
            s3_url = _upload_artifact_to_s3(job_id, filename, video_bytes)
        except Exception as exc:
            errors.append(f"Error uploading {filename} from output directory: {exc}")
            continue

        print(f"worker-comfyui - Uploaded fallback video artifact: {filename}")
        videos.append({"filename": filename, "type": "s3_url", "data": s3_url})

    if not videos:
        errors.append(
            f"No recent video files found under {', '.join(scanned_output_dirs)} "
            f"for prefix {filename_prefix}"
        )
    return videos, errors


def _resolve_dimensions(
    aspect_ratio, width, height, default_width=1024, default_height=1024
):
    if width and height:
        return int(width), int(height)

    if aspect_ratio:
        preset = ASPECT_RATIO_PRESETS.get(str(aspect_ratio).strip())
        if preset:
            return preset

    return default_width, default_height


def _set_prompt_fields(workflow, prompt=None, negative_prompt=None):
    for node in workflow.values():
        inputs = node.get("inputs", {})
        class_type = node.get("class_type", "")
        title = ((node.get("_meta") or {}).get("title", "")).lower()

        if class_type == "CLIPTextEncode" and "text" in inputs:
            if "negative" in title and negative_prompt is not None:
                inputs["text"] = negative_prompt
            elif "positive" in title and prompt is not None:
                inputs["text"] = prompt
            elif prompt is not None and "negative" not in title:
                # Fallback for single prompt encoder graphs
                inputs["text"] = prompt


def _set_numeric_fields(workflow, width, height, count, options):
    for node in workflow.values():
        inputs = node.get("inputs", {})
        class_type = node.get("class_type", "")

        if width is not None and "width" in inputs:
            inputs["width"] = int(width)
        if height is not None and "height" in inputs:
            inputs["height"] = int(height)
        if count is not None and "batch_size" in inputs:
            inputs["batch_size"] = int(count)

        if "steps" in options and "steps" in inputs:
            inputs["steps"] = int(options["steps"])

        if "seed" in options:
            if "noise_seed" in inputs:
                inputs["noise_seed"] = int(options["seed"])
            if "seed" in inputs:
                inputs["seed"] = int(options["seed"])

        if "cfg" in options:
            if "cfg" in inputs:
                inputs["cfg"] = float(options["cfg"])
            if class_type == "FluxGuidance" and "guidance" in inputs:
                inputs["guidance"] = float(options["cfg"])

        if "denoise" in options and "denoise" in inputs:
            inputs["denoise"] = float(options["denoise"])

        if "sampler_name" in options and "sampler_name" in inputs:
            inputs["sampler_name"] = options["sampler_name"]


def _set_i2i_image_fields(workflow, image_name):
    for node in workflow.values():
        inputs = node.get("inputs", {})
        class_type = node.get("class_type", "")
        if class_type == "LoadImage" and "image" in inputs:
            inputs["image"] = image_name


def _load_model_presets():
    raw = os.environ.get("FLUX_MODEL_PRESETS_JSON")
    if not raw:
        return DEFAULT_FLUX_MODEL_PRESETS
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return DEFAULT_FLUX_MODEL_PRESETS


def _load_model_assets():
    raw = os.environ.get("FLUX_MODEL_ASSETS_JSON")
    if not raw:
        return DEFAULT_FLUX_MODEL_ASSETS
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return DEFAULT_FLUX_MODEL_ASSETS


def _download_file(url, destination, hf_token=None):
    os.makedirs(os.path.dirname(destination), exist_ok=True)

    headers = {}
    if hf_token:
        headers["Authorization"] = f"Bearer {hf_token}"

    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=600) as response:
        with open(destination, "wb") as out_file:
            out_file.write(response.read())


def _ensure_model_assets(model_name):
    assets_by_model = _load_model_assets()
    assets = assets_by_model.get(model_name)
    if not assets:
        return False, (
            f"No runtime asset manifest found for model '{model_name}'. "
            "Set FLUX_MODEL_ASSETS_JSON to configure download paths/urls."
        )

    comfy_root = os.environ.get("COMFY_ROOT", "/comfyui")
    hf_token = os.environ.get("HUGGINGFACE_ACCESS_TOKEN") or os.environ.get(
        "HF_TOKEN"
    )

    for asset in assets:
        rel_path = asset.get("path")
        url = asset.get("url")
        if not rel_path or not url:
            return False, f"Invalid asset entry for model '{model_name}': {asset}"

        local_path = os.path.join(comfy_root, rel_path)
        if os.path.exists(local_path):
            continue

        print(
            f"worker-comfyui - Model asset missing for {model_name}, downloading: {rel_path}"
        )
        try:
            _download_file(url, local_path, hf_token=hf_token)
            print(f"worker-comfyui - Downloaded: {rel_path}")
        except Exception as e:
            return False, f"Failed downloading {rel_path}: {e}"

    return True, None


def _apply_model_preset(workflow, model_name):
    presets = _load_model_presets()
    preset = presets.get(model_name)
    if not preset:
        return False, f"Unsupported model '{model_name}'. Available: {', '.join(presets.keys())}"

    for node in workflow.values():
        class_type = node.get("class_type", "")
        inputs = node.get("inputs", {})

        if class_type == "UNETLoader" and preset.get("unet_name"):
            inputs["unet_name"] = preset["unet_name"]
        elif class_type == "CLIPLoader" and preset.get("clip_name"):
            inputs["clip_name"] = preset["clip_name"]
        elif class_type == "VAELoader" and preset.get("vae_name"):
            inputs["vae_name"] = preset["vae_name"]

    return True, None


def _build_custom_mode_input(job_input, mode):
    workflow_path = (
        FLUX2_T2I_WORKFLOW_PATH if mode == "t2i" else FLUX2_I2I_WORKFLOW_PATH
    )

    try:
        workflow = _load_workflow_template(workflow_path)
    except Exception as e:
        return None, f"Unable to load workflow template ({workflow_path}): {e}"

    prompt = job_input.get("prompt")
    if not prompt:
        return None, "Missing 'prompt' parameter"

    options = job_input.get("options") or {}
    if not isinstance(options, dict):
        return None, "'options' must be an object"

    count = job_input.get("count", 1)
    try:
        count = int(count)
    except Exception:
        return None, "'count' must be an integer"
    if count < 1:
        return None, "'count' must be >= 1"

    default_width = None if mode == "i2i" else 1024
    default_height = None if mode == "i2i" else 1024
    width, height = _resolve_dimensions(
        job_input.get("aspect_ratio"),
        job_input.get("width"),
        job_input.get("height"),
        default_width=default_width,
        default_height=default_height,
    )

    _set_prompt_fields(
        workflow,
        prompt=prompt,
        negative_prompt=job_input.get("negative_prompt"),
    )

    model_name = options.get("model") or job_input.get("model")
    if model_name:
        ok, model_error = _apply_model_preset(workflow, model_name)
        if not ok:
            return None, model_error

    _set_numeric_fields(workflow, width, height, count, options)

    images = None
    if mode == "i2i":
        image_value = job_input.get("image")
        image_name = job_input.get("image_name", "input_image.png")

        # Allow either `image` or existing `images` format
        if image_value:
            images = [{"name": image_name, "image": image_value}]
        elif job_input.get("images"):
            images = job_input.get("images")
            if not isinstance(images, list) or not all(
                "name" in img and "image" in img for img in images
            ):
                return (
                    None,
                    "'images' must be a list of objects with 'name' and 'image' keys",
                )
            image_name = images[0]["name"]
        else:
            return None, "Missing 'image' (or 'images') parameter for i2i mode"

        _set_i2i_image_fields(workflow, image_name)

    return {
        "workflow": workflow,
        "images": images,
        "comfy_org_api_key": job_input.get("comfy_org_api_key"),
        "selected_model": model_name,
    }, None


def _get_comfyui_pid():
    """Read the ComfyUI process PID from the PID file written by start.sh."""
    try:
        with open(COMFY_PID_FILE, "r") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def _is_comfyui_process_alive():
    """Check whether the ComfyUI process is still running.

    Returns True if alive, False if dead, None if PID file not found.
    """
    pid = _get_comfyui_pid()
    if pid is None:
        return None
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # process exists but we can't signal it


def check_server(url, retries=0, delay=50):
    """
    Check if a server is reachable via HTTP GET request.

    When a PID file is available (written by start.sh), the function polls
    indefinitely while the ComfyUI process is alive and fails immediately
    when the process exits.  When no PID file is found it falls back to
    the retry limit for backward compatibility.

    Args:
        url (str): The URL to check.
        retries (int): Max attempts. 0 means unlimited (poll while process alive).
        delay (int): Time in milliseconds between retries.

    Returns:
        bool: True if the server is reachable, False otherwise.
    """
    print(f"worker-comfyui - Checking API server at {url}...")

    # Guard against zero/negative delay to avoid division by zero
    delay = max(1, delay)
    # How often to print a "still waiting" log (every ~10 seconds)
    log_every = max(1, int(10_000 / delay))
    attempt = 0

    while True:
        # --- Check if ComfyUI process is still alive ---
        process_status = _is_comfyui_process_alive()
        if process_status is False:
            print(
                "worker-comfyui - ComfyUI process has exited. "
                "Server will not become reachable."
            )
            return False

        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print(f"worker-comfyui - API is reachable")
                return True
        except requests.Timeout:
            pass
        except requests.RequestException:
            pass

        attempt += 1

        # If we can't track the process, enforce a retry limit to avoid
        # hanging forever when the PID file is never written
        fallback = retries if retries > 0 else COMFY_API_FALLBACK_MAX_RETRIES
        if process_status is None and attempt >= fallback:
            print(
                f"worker-comfyui - Failed to connect to server at {url} "
                f"after {fallback} attempts (no PID file found)."
            )
            return False

        if attempt % log_every == 0:
            elapsed_s = (attempt * delay) / 1000
            print(
                f"worker-comfyui - Still waiting for API server... "
                f"({elapsed_s:.0f}s elapsed, attempt {attempt})"
            )

        time.sleep(delay / 1000)


def upload_images(images):
    """
    Upload a list of base64 encoded images to the ComfyUI server using the /upload/image endpoint.

    Args:
        images (list): A list of dictionaries, each containing the 'name' of the image and the 'image' as a base64 encoded string.

    Returns:
        dict: A dictionary indicating success or error.
    """
    if not images:
        return {"status": "success", "message": "No images to upload", "details": []}

    responses = []
    upload_errors = []

    print(f"worker-comfyui - Uploading {len(images)} image(s)...")

    for image in images:
        try:
            name = image["name"]
            image_data_uri = image["image"]  # Get the full string (might have prefix)

            # --- Strip Data URI prefix if present ---
            if "," in image_data_uri:
                # Find the comma and take everything after it
                base64_data = image_data_uri.split(",", 1)[1]
            else:
                # Assume it's already pure base64
                base64_data = image_data_uri
            # --- End strip ---

            blob = base64.b64decode(base64_data)  # Decode the cleaned data

            # Prepare the form data
            files = {
                "image": (name, BytesIO(blob), "image/png"),
                "overwrite": (None, "true"),
            }

            # POST request to upload the image
            response = requests.post(
                f"http://{COMFY_HOST}/upload/image", files=files, timeout=30
            )
            response.raise_for_status()

            responses.append(f"Successfully uploaded {name}")
            print(f"worker-comfyui - Successfully uploaded {name}")

        except base64.binascii.Error as e:
            error_msg = f"Error decoding base64 for {image.get('name', 'unknown')}: {e}"
            print(f"worker-comfyui - {error_msg}")
            upload_errors.append(error_msg)
        except requests.Timeout:
            error_msg = f"Timeout uploading {image.get('name', 'unknown')}"
            print(f"worker-comfyui - {error_msg}")
            upload_errors.append(error_msg)
        except requests.RequestException as e:
            error_msg = f"Error uploading {image.get('name', 'unknown')}: {e}"
            print(f"worker-comfyui - {error_msg}")
            upload_errors.append(error_msg)
        except Exception as e:
            error_msg = (
                f"Unexpected error uploading {image.get('name', 'unknown')}: {e}"
            )
            print(f"worker-comfyui - {error_msg}")
            upload_errors.append(error_msg)

    if upload_errors:
        print(f"worker-comfyui - image(s) upload finished with errors")
        return {
            "status": "error",
            "message": "Some images failed to upload",
            "details": upload_errors,
        }

    print(f"worker-comfyui - image(s) upload complete")
    return {
        "status": "success",
        "message": "All images uploaded successfully",
        "details": responses,
    }


def get_available_models():
    """
    Get list of available models from ComfyUI

    Returns:
        dict: Dictionary containing available models by type
    """
    try:
        response = requests.get(f"http://{COMFY_HOST}/object_info", timeout=10)
        response.raise_for_status()
        object_info = response.json()

        # Extract available checkpoints from CheckpointLoaderSimple
        available_models = {}
        if "CheckpointLoaderSimple" in object_info:
            checkpoint_info = object_info["CheckpointLoaderSimple"]
            if "input" in checkpoint_info and "required" in checkpoint_info["input"]:
                ckpt_options = checkpoint_info["input"]["required"].get("ckpt_name")
                if ckpt_options and len(ckpt_options) > 0:
                    available_models["checkpoints"] = (
                        ckpt_options[0] if isinstance(ckpt_options[0], list) else []
                    )

        return available_models
    except Exception as e:
        print(f"worker-comfyui - Warning: Could not fetch available models: {e}")
        return {}


def queue_workflow(workflow, client_id, comfy_org_api_key=None):
    """
    Queue a workflow to be processed by ComfyUI

    Args:
        workflow (dict): A dictionary containing the workflow to be processed
        client_id (str): The client ID for the websocket connection
        comfy_org_api_key (str, optional): Comfy.org API key for API Nodes

    Returns:
        dict: The JSON response from ComfyUI after processing the workflow

    Raises:
        ValueError: If the workflow validation fails with detailed error information
    """
    # Include client_id in the prompt payload
    payload = {"prompt": workflow, "client_id": client_id}

    # Optionally inject Comfy.org API key for API Nodes.
    # Precedence: per-request key (argument) overrides environment variable.
    # Note: We use our consistent naming (comfy_org_api_key) but transform to
    # ComfyUI's expected format (api_key_comfy_org) when sending.
    key_from_env = os.environ.get("COMFY_ORG_API_KEY")
    effective_key = comfy_org_api_key if comfy_org_api_key else key_from_env
    if effective_key:
        payload["extra_data"] = {"api_key_comfy_org": effective_key}
    data = json.dumps(payload).encode("utf-8")

    # Use requests for consistency and timeout
    headers = {"Content-Type": "application/json"}
    response = requests.post(
        f"http://{COMFY_HOST}/prompt", data=data, headers=headers, timeout=30
    )

    # Handle validation errors with detailed information
    if response.status_code == 400:
        print(f"worker-comfyui - ComfyUI returned 400. Response body: {response.text}")
        try:
            error_data = response.json()
            print(f"worker-comfyui - Parsed error data: {error_data}")

            # Try to extract meaningful error information
            error_message = "Workflow validation failed"
            error_details = []

            # ComfyUI seems to return different error formats, let's handle them all
            if "error" in error_data:
                error_info = error_data["error"]
                if isinstance(error_info, dict):
                    error_message = error_info.get("message", error_message)
                    if error_info.get("type") == "prompt_outputs_failed_validation":
                        error_message = "Workflow validation failed"
                else:
                    error_message = str(error_info)

            # Check for node validation errors in the response
            if "node_errors" in error_data:
                for node_id, node_error in error_data["node_errors"].items():
                    if isinstance(node_error, dict):
                        for error_type, error_msg in node_error.items():
                            error_details.append(
                                f"Node {node_id} ({error_type}): {error_msg}"
                            )
                    else:
                        error_details.append(f"Node {node_id}: {node_error}")

            # Check if the error data itself contains validation info
            if error_data.get("type") == "prompt_outputs_failed_validation":
                error_message = error_data.get("message", "Workflow validation failed")
                # For this type of error, we need to parse the validation details from logs
                # Since ComfyUI doesn't seem to include detailed validation errors in the response
                # Let's provide a more helpful generic message
                available_models = get_available_models()
                if available_models.get("checkpoints"):
                    error_message += f"\n\nThis usually means a required model or parameter is not available."
                    error_message += f"\nAvailable checkpoint models: {', '.join(available_models['checkpoints'])}"
                else:
                    error_message += "\n\nThis usually means a required model or parameter is not available."
                    error_message += "\nNo checkpoint models appear to be available. Please check your model installation."

                raise ValueError(error_message)

            # If we have specific validation errors, format them nicely
            if error_details:
                detailed_message = f"{error_message}:\n" + "\n".join(
                    f"• {detail}" for detail in error_details
                )

                # Try to provide helpful suggestions for common errors
                if any(
                    "not in list" in detail and "ckpt_name" in detail
                    for detail in error_details
                ):
                    available_models = get_available_models()
                    if available_models.get("checkpoints"):
                        detailed_message += f"\n\nAvailable checkpoint models: {', '.join(available_models['checkpoints'])}"
                    else:
                        detailed_message += "\n\nNo checkpoint models appear to be available. Please check your model installation."

                raise ValueError(detailed_message)
            else:
                # Fallback to the raw response if we can't parse specific errors
                raise ValueError(f"{error_message}. Raw response: {response.text}")

        except (json.JSONDecodeError, KeyError) as e:
            # If we can't parse the error response, fall back to the raw text
            raise ValueError(
                f"ComfyUI validation failed (could not parse error response): {response.text}"
            )

    # For other HTTP errors, raise them normally
    response.raise_for_status()
    return response.json()


def get_history(prompt_id):
    """
    Retrieve the history of a given prompt using its ID

    Args:
        prompt_id (str): The ID of the prompt whose history is to be retrieved

    Returns:
        dict: The history of the prompt, containing all the processing steps and results
    """
    # Use requests for consistency and timeout
    response = requests.get(f"http://{COMFY_HOST}/history/{prompt_id}", timeout=30)
    response.raise_for_status()
    return response.json()


def get_image_data(filename, subfolder, image_type):
    """
    Fetch image bytes from the ComfyUI /view endpoint.

    Args:
        filename (str): The filename of the image.
        subfolder (str): The subfolder where the image is stored.
        image_type (str): The type of the image (e.g., 'output').

    Returns:
        bytes: The raw image data, or None if an error occurs.
    """
    print(
        f"worker-comfyui - Fetching image data: type={image_type}, subfolder={subfolder}, filename={filename}"
    )
    data = {"filename": filename, "subfolder": subfolder, "type": image_type}
    url_values = urllib.parse.urlencode(data)
    try:
        # Use requests for consistency and timeout
        response = requests.get(f"http://{COMFY_HOST}/view?{url_values}", timeout=60)
        response.raise_for_status()
        print(f"worker-comfyui - Successfully fetched image data for {filename}")
        return response.content
    except requests.Timeout:
        print(f"worker-comfyui - Timeout fetching image data for {filename}")
        return None
    except requests.RequestException as e:
        print(f"worker-comfyui - Error fetching image data for {filename}: {e}")
        return None
    except Exception as e:
        print(
            f"worker-comfyui - Unexpected error fetching image data for {filename}: {e}"
        )
        return None


def handler(job):
    """
    Handles a job using ComfyUI via websockets for status and image retrieval.

    Args:
        job (dict): A dictionary containing job details and input parameters.

    Returns:
        dict: A dictionary containing either an error message or a success status with generated images.
    """
    # ---------------------------------------------------------------------------
    # Network Volume Diagnostics (opt-in via NETWORK_VOLUME_DEBUG=true)
    # ---------------------------------------------------------------------------
    if is_network_volume_debug_enabled():
        run_network_volume_diagnostics()

    job_input = job["input"]
    job_id = job["id"]

    # Make sure that the input is valid
    validated_data, error_message = validate_input(job_input)
    if error_message:
        return {"error": error_message}

    # Extract validated data
    workflow = validated_data["workflow"]
    input_images = validated_data.get("images")
    remote_images = validated_data.get("remote_images") or []
    selected_model = validated_data.get("selected_model")
    video_meta = validated_data.get("meta", {})
    video_mode = video_meta.get("mode")
    video_filename_prefix = None
    if video_mode in VIDEO_MODES:
        video_filename_prefix = _video_filename_prefix(video_mode, job_id)
        _set_video_save_fields(
            workflow,
            video_mode,
            video_meta.get("fps", DEFAULT_VIDEO_OPTIONS["fps"]),
            job_id=job_id,
        )

    ok, model_error = _check_wan22_model_assets()
    if not ok:
        return {"error": model_error}

    # For custom API: verify model assets are present, download once if missing
    if selected_model:
        ok, model_error = _ensure_model_assets(selected_model)
        if not ok:
            return {"error": model_error}

    # Make sure that the ComfyUI HTTP API is available before proceeding
    if not check_server(
        f"http://{COMFY_HOST}/",
        COMFY_API_AVAILABLE_MAX_RETRIES,
        COMFY_API_AVAILABLE_INTERVAL_MS,
    ):
        return {
            "error": f"ComfyUI server ({COMFY_HOST}) not reachable after multiple retries."
        }

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

    # Upload input images if they exist
    if input_images:
        upload_result = upload_images(input_images)
        if upload_result["status"] == "error":
            # Return upload errors
            return {
                "error": {
                    "code": "ASSET_UPLOAD_FAILED",
                    "message": "Failed to upload one or more input images",
                    "details": upload_result["details"],
                }
            }

    ws = None
    client_id = str(uuid.uuid4())
    prompt_id = None
    output_videos = []
    errors = []
    job_started_at = time.time()

    try:
        # Establish WebSocket connection
        ws_url = f"ws://{COMFY_HOST}/ws?clientId={client_id}"
        print(f"worker-comfyui - Connecting to websocket: {ws_url}")
        ws = websocket.WebSocket()
        ws.connect(ws_url, timeout=10)
        print(f"worker-comfyui - Websocket connected")

        # Queue the workflow
        try:
            # Pass per-request API key if provided in input
            queued_workflow = queue_workflow(
                workflow,
                client_id,
                comfy_org_api_key=validated_data.get("comfy_org_api_key"),
            )
            prompt_id = queued_workflow.get("prompt_id")
            if not prompt_id:
                raise ValueError(
                    f"Missing 'prompt_id' in queue response: {queued_workflow}"
                )
            print(f"worker-comfyui - Queued workflow with ID: {prompt_id}")
        except requests.RequestException as e:
            print(f"worker-comfyui - Error queuing workflow: {e}")
            raise ValueError(f"Error queuing workflow: {e}")
        except Exception as e:
            print(f"worker-comfyui - Unexpected error queuing workflow: {e}")
            # For ValueError exceptions from queue_workflow, pass through the original message
            if isinstance(e, ValueError):
                raise e
            else:
                raise ValueError(f"Unexpected error queuing workflow: {e}")

        # Wait for execution completion via WebSocket
        print(f"worker-comfyui - Waiting for workflow execution ({prompt_id})...")
        execution_done = False
        while True:
            try:
                out = ws.recv()
                if isinstance(out, str):
                    message = json.loads(out)
                    if message.get("type") == "status":
                        status_data = message.get("data", {}).get("status", {})
                        print(
                            f"worker-comfyui - Status update: {status_data.get('exec_info', {}).get('queue_remaining', 'N/A')} items remaining in queue"
                        )
                    elif message.get("type") == "executing":
                        data = message.get("data", {})
                        if (
                            data.get("node") is None
                            and data.get("prompt_id") == prompt_id
                        ):
                            print(
                                f"worker-comfyui - Execution finished for prompt {prompt_id}"
                            )
                            execution_done = True
                            break
                    elif message.get("type") == "execution_error":
                        data = message.get("data", {})
                        if data.get("prompt_id") == prompt_id:
                            error_details = f"Node Type: {data.get('node_type')}, Node ID: {data.get('node_id')}, Message: {data.get('exception_message')}"
                            print(
                                f"worker-comfyui - Execution error received: {error_details}"
                            )
                            errors.append(f"Workflow execution error: {error_details}")
                            break
                else:
                    continue
            except websocket.WebSocketTimeoutException:
                print(f"worker-comfyui - Websocket receive timed out. Still waiting...")
                continue
            except websocket.WebSocketConnectionClosedException as closed_err:
                try:
                    # Attempt to reconnect
                    ws = _attempt_websocket_reconnect(
                        ws_url,
                        WEBSOCKET_RECONNECT_ATTEMPTS,
                        WEBSOCKET_RECONNECT_DELAY_S,
                        closed_err,
                    )

                    print(
                        "worker-comfyui - Resuming message listening after successful reconnect."
                    )
                    continue
                except (
                    websocket.WebSocketConnectionClosedException
                ) as reconn_failed_err:
                    # If _attempt_websocket_reconnect fails, it raises this exception
                    # Let this exception propagate to the outer handler's except block
                    raise reconn_failed_err

            except json.JSONDecodeError:
                print(f"worker-comfyui - Received invalid JSON message via websocket.")

        if not execution_done and not errors:
            raise ValueError(
                "Workflow monitoring loop exited without confirmation of completion or error."
            )

        # Fetch history even if there were execution errors, some outputs might exist
        print(f"worker-comfyui - Fetching history for prompt {prompt_id}...")
        history = get_history(prompt_id)

        if prompt_id not in history:
            error_msg = f"Prompt ID {prompt_id} not found in history after execution."
            print(f"worker-comfyui - {error_msg}")
            if not errors:
                return {"error": error_msg}
            else:
                errors.append(error_msg)
                return {
                    "error": "Job processing failed, prompt ID not found in history.",
                    "details": errors,
                }

        prompt_history = history.get(prompt_id, {})
        outputs = prompt_history.get("outputs", {})

        if not outputs:
            warning_msg = f"No outputs found in history for prompt {prompt_id}."
            print(f"worker-comfyui - {warning_msg}")
            if not errors:
                errors.append(warning_msg)

        print(f"worker-comfyui - Processing {len(outputs)} output nodes...")
        output_videos, output_errors = _collect_video_outputs(job_id, outputs)
        errors.extend(output_errors)
        if not output_videos and video_filename_prefix:
            output_keys = {
                node_id: sorted((node_output or {}).keys())
                for node_id, node_output in outputs.items()
            }
            print(
                "worker-comfyui - No video artifacts found in history; "
                f"history output keys: {output_keys}. Falling back to output directory scan."
            )
            fallback_videos, fallback_errors = _collect_recent_video_files(
                job_id,
                since_epoch=job_started_at - 5,
                filename_prefix=video_filename_prefix,
            )
            output_videos.extend(fallback_videos)
            if fallback_videos:
                errors = [
                    error
                    for error in errors
                    if not error.startswith("No recent video files found")
                ]
            else:
                errors.extend(fallback_errors)

    except websocket.WebSocketException as e:
        print(f"worker-comfyui - WebSocket Error: {e}")
        print(traceback.format_exc())
        return {"error": f"WebSocket communication error: {e}"}
    except requests.RequestException as e:
        print(f"worker-comfyui - HTTP Request Error: {e}")
        print(traceback.format_exc())
        return {"error": f"HTTP communication error with ComfyUI: {e}"}
    except ValueError as e:
        print(f"worker-comfyui - Value Error: {e}")
        print(traceback.format_exc())
        return {"error": str(e)}
    except Exception as e:
        print(f"worker-comfyui - Unexpected Handler Error: {e}")
        print(traceback.format_exc())
        return {"error": f"An unexpected error occurred: {e}"}
    finally:
        if ws and ws.connected:
            print(f"worker-comfyui - Closing websocket connection.")
            ws.close()

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
        print(f"worker-comfyui - Job failed with no output videos.")
        return {
            "error": {
                "code": "OUTPUT_NOT_FOUND",
                "message": "Job processing failed with no output videos",
                "details": errors,
            }
        }

    print(f"worker-comfyui - Job completed. Returning {len(output_videos)} video(s).")
    return final_result


if __name__ == "__main__":
    print("worker-comfyui - Starting handler...")
    runpod.serverless.start({"handler": handler})
