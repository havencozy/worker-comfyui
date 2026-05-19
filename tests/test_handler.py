import base64
import json
import os
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import MagicMock, Mock, patch


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(REPO_ROOT, "src")
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, SRC_DIR)


def _install_runpod_stub():
    runpod_module = types.ModuleType("runpod")
    serverless_module = types.ModuleType("runpod.serverless")
    utils_module = types.ModuleType("runpod.serverless.utils")

    serverless_module.start = Mock()
    serverless_module.utils = utils_module
    runpod_module.serverless = serverless_module

    sys.modules.setdefault("runpod", runpod_module)
    sys.modules.setdefault("runpod.serverless", serverless_module)
    sys.modules.setdefault("runpod.serverless.utils", utils_module)


def _install_websocket_stub():
    try:
        __import__("websocket")
        return
    except ModuleNotFoundError:
        pass

    websocket_module = types.ModuleType("websocket")

    class WebSocketException(Exception):
        pass

    class WebSocketTimeoutException(WebSocketException):
        pass

    class WebSocketConnectionClosedException(WebSocketException):
        pass

    class WebSocket:
        connected = False

        def connect(self, *args, **kwargs):
            self.connected = True

        def close(self):
            self.connected = False

    websocket_module.WebSocketException = WebSocketException
    websocket_module.WebSocketTimeoutException = WebSocketTimeoutException
    websocket_module.WebSocketConnectionClosedException = (
        WebSocketConnectionClosedException
    )
    websocket_module.WebSocket = WebSocket
    websocket_module.enableTrace = Mock()
    sys.modules.setdefault("websocket", websocket_module)


_install_runpod_stub()
_install_websocket_stub()
import handler


RUNPOD_WORKER_COMFY_TEST_RESOURCES_IMAGES = "./test_resources/images"


class TestRunpodWorkerComfy(unittest.TestCase):
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
                "HUNYUAN_T2V_WORKFLOW_PATH": os.path.join(
                    REPO_ROOT, "test_resources/workflows/hunyuan_video_test_t2v.json"
                ),
                "HUNYUAN_I2V_WORKFLOW_PATH": os.path.join(
                    REPO_ROOT, "test_resources/workflows/hunyuan_video_test_i2v.json"
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

    def test_wan22_t2v_alias_builds_video_workflow(self):
        input_data = {
            "mode": "wan22-t2v",
            "prompt": "neon dragon over a rainy skyline",
            "resolution": "480p",
            "aspect_ratio": "16:9",
            "options": {"length": 81, "steps": 30, "seed": 42},
        }

        validated_data, error = handler.validate_input(input_data)

        self.assertIsNone(error)
        self.assertEqual(validated_data["meta"]["mode"], "t2v")
        self.assertEqual(validated_data["meta"]["width"], 848)
        self.assertEqual(validated_data["meta"]["height"], 480)
        self.assertEqual(validated_data["meta"]["num_frames"], 81)
        self.assertEqual(validated_data["meta"]["seed"], 42)
        self.assertEqual(
            validated_data["workflow"]["6"]["inputs"]["text"], input_data["prompt"]
        )
        self.assertEqual(validated_data["workflow"]["55"]["inputs"]["length"], 81)
        self.assertEqual(validated_data["workflow"]["57"]["inputs"]["noise_seed"], 42)

    def test_hunyuan_t2v_alias_builds_hunyuan_workflow(self):
        input_data = {
            "mode": "hunyuan-t2v",
            "prompt": "a glass apple rotating on a studio table",
            "negative_prompt": "blur",
            "resolution": "480p",
            "aspect_ratio": "1:1",
            "options": {"fps": 24, "steps": 30, "guidance_scale": 6.5, "length": 97},
            "seed": 42,
            "hf_token": "hf-request-token",
        }

        validated_data, error = handler.validate_input(input_data)

        self.assertIsNone(error)
        self.assertEqual(validated_data["meta"]["mode"], "t2v")
        self.assertEqual(validated_data["meta"]["model"], "hunyuanvideo-1.5")
        workflow = validated_data["workflow"]
        self.assertEqual(workflow["1"]["inputs"]["resolution"], "480p")
        self.assertEqual(workflow["1"]["inputs"]["task"], "t2v")
        self.assertEqual(workflow["1"]["inputs"]["hf_token"], "hf-request-token")
        self.assertEqual(workflow["2"]["inputs"]["prompt"], input_data["prompt"])
        self.assertEqual(
            workflow["2"]["inputs"]["negative_prompt"], input_data["negative_prompt"]
        )
        self.assertEqual(workflow["2"]["inputs"]["video_length"], 97)
        self.assertEqual(workflow["2"]["inputs"]["num_inference_steps"], 30)
        self.assertEqual(workflow["2"]["inputs"]["guidance_scale"], 6.5)
        self.assertEqual(workflow["2"]["inputs"]["aspect_ratio"], "1:1")
        self.assertEqual(workflow["2"]["inputs"]["seed"], 42)
        self.assertEqual(
            workflow["4"]["inputs"]["filename_prefix"], "video/hunyuan_t2v"
        )

    def test_hunyuan_i2v_alias_accepts_start_frame(self):
        input_data = {
            "mode": "hunyuan-i2v",
            "prompt": "animate the portrait",
            "start_frame": "data:image/png;base64,ZmFrZQ==",
            "start_frame_name": "portrait.png",
        }

        validated_data, error = handler.validate_input(input_data)

        self.assertIsNone(error)
        self.assertEqual(validated_data["meta"]["mode"], "i2v")
        self.assertEqual(validated_data["meta"]["model"], "hunyuanvideo-1.5")
        self.assertEqual(
            validated_data["images"],
            [{"name": "portrait.png", "image": input_data["start_frame"]}],
        )
        self.assertEqual(
            validated_data["workflow"]["2"]["inputs"]["image"], "portrait.png"
        )
        self.assertEqual(validated_data["workflow"]["1"]["inputs"]["task"], "i2v")

    def test_hunyuan_rejects_1080p_resolution(self):
        validated_data, error = handler.validate_input(
            {
                "mode": "hunyuan-t2v",
                "prompt": "clean cinematic motion",
                "resolution": "1080p",
            }
        )

        self.assertIsNone(validated_data)
        self.assertEqual(error["code"], "VALIDATION_ERROR")
        self.assertIn("480p, 720p", error["message"])

    def test_video_input_passes_per_request_comfy_org_api_key(self):
        input_data = {
            "mode": "t2v",
            "prompt": "clean cinematic motion",
            "api_key_comfy_org": "request-key",
        }

        validated_data, error = handler.validate_input(input_data)

        self.assertIsNone(error)
        self.assertEqual(validated_data["comfy_org_api_key"], "request-key")

    def test_wan22_i2v_alias_accepts_start_frame(self):
        input_data = {
            "mode": "wan22-i2v",
            "prompt": "add subtle cinematic motion",
            "start_frame": "data:image/png;base64,ZmFrZQ==",
            "start_frame_name": "portrait.png",
        }

        validated_data, error = handler.validate_input(input_data)

        self.assertIsNone(error)
        self.assertEqual(validated_data["meta"]["mode"], "i2v")
        self.assertEqual(
            validated_data["images"],
            [{"name": "portrait.png", "image": input_data["start_frame"]}],
        )
        self.assertEqual(
            validated_data["workflow"]["56"]["inputs"]["image"], "portrait.png"
        )

    def test_wan22_flf2v_alias_accepts_start_and_end_frames(self):
        input_data = {
            "mode": "wan22-flf2v",
            "prompt": "move from first frame to last frame",
            "start_frame": "data:image/png;base64,c3RhcnQ=",
            "end_frame": "data:image/png;base64,ZW5k",
        }

        validated_data, error = handler.validate_input(input_data)

        self.assertIsNone(error)
        self.assertEqual(validated_data["meta"]["mode"], "r2v")
        self.assertEqual(
            validated_data["images"],
            [
                {"name": "start_frame.png", "image": input_data["start_frame"]},
                {"name": "end_frame.png", "image": input_data["end_frame"]},
            ],
        )

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

    def test_set_video_save_fields_can_scope_filename_prefix_to_job_id(self):
        workflow = {
            "1": {
                "class_type": "SaveVideo",
                "inputs": {"filename_prefix": "video/ComfyUI", "fps": 16},
            },
            "2": {"class_type": "CreateVideo", "inputs": {"fps": 16}},
        }

        handler._set_video_save_fields(workflow, "t2v", 24, job_id="job-123")

        self.assertEqual(
            workflow["1"]["inputs"]["filename_prefix"], "video/job-123_wan22_t2v"
        )
        self.assertEqual(workflow["1"]["inputs"]["fps"], 24)
        self.assertEqual(workflow["2"]["inputs"]["fps"], 24)

    def test_set_video_sampler_fields_splits_wan22_dual_sampler_steps(self):
        workflow = {
            "high": {
                "class_type": "KSamplerAdvanced",
                "_meta": {"title": "KSampler Advanced High Noise"},
                "inputs": {
                    "noise_seed": 1,
                    "steps": 20,
                    "cfg": 3.5,
                    "start_at_step": 0,
                    "end_at_step": 10,
                },
            },
            "low": {
                "class_type": "KSamplerAdvanced",
                "_meta": {"title": "KSampler Advanced Low Noise"},
                "inputs": {
                    "noise_seed": 0,
                    "steps": 20,
                    "cfg": 3.5,
                    "start_at_step": 10,
                    "end_at_step": 10000,
                },
            },
        }

        handler._set_video_sampler_fields(
            workflow,
            seed=42,
            options={"steps": 30, "guidance_scale": 7.5},
        )

        self.assertEqual(workflow["high"]["inputs"]["noise_seed"], 42)
        self.assertEqual(workflow["high"]["inputs"]["steps"], 30)
        self.assertEqual(workflow["high"]["inputs"]["cfg"], 7.5)
        self.assertEqual(workflow["high"]["inputs"]["start_at_step"], 0)
        self.assertEqual(workflow["high"]["inputs"]["end_at_step"], 15)

        self.assertEqual(workflow["low"]["inputs"]["noise_seed"], 42)
        self.assertEqual(workflow["low"]["inputs"]["steps"], 30)
        self.assertEqual(workflow["low"]["inputs"]["cfg"], 7.5)
        self.assertEqual(workflow["low"]["inputs"]["start_at_step"], 15)
        self.assertEqual(workflow["low"]["inputs"]["end_at_step"], 10000)

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

    def test_non_video_modes_are_not_supported(self):
        validated_data, error = handler.validate_input(
            {"mode": "not-video", "prompt": "old non-video mode"}
        )

        self.assertIsNone(validated_data)
        self.assertEqual(error["code"], "UNSUPPORTED_MODE")

    @patch("handler.os.path.exists", return_value=True)
    def test_wan22_model_preflight_passes_when_required_files_exist(self, mock_exists):
        ok, error = handler._check_wan22_model_assets()

        self.assertTrue(ok)
        self.assertIsNone(error)
        checked_paths = [call.args[0] for call in mock_exists.call_args_list]
        self.assertIn(
            "/runpod-volume/models/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors",
            checked_paths,
        )

    @patch("handler.os.path.exists")
    def test_wan22_model_preflight_reports_missing_files(self, mock_exists):
        def exists(path):
            return "umt5_xxl_fp8_e4m3fn_scaled.safetensors" not in path

        mock_exists.side_effect = exists

        ok, error = handler._check_wan22_model_assets()

        self.assertFalse(ok)
        self.assertEqual(error["code"], "MODEL_ASSET_MISSING")
        self.assertIn("umt5_xxl_fp8_e4m3fn_scaled.safetensors", error["message"])

    @patch("handler.check_server")
    @patch("handler._check_video_model_assets")
    def test_handler_returns_missing_model_before_server_check(
        self, mock_preflight, mock_check_server
    ):
        mock_preflight.return_value = (
            False,
            {
                "code": "MODEL_ASSET_MISSING",
                "message": "Missing Wan2.2 model files: models/vae/wan_2.1_vae.safetensors",
            },
        )

        result = handler.handler(
            {"id": "job-1", "input": {"mode": "t2v", "prompt": "test video"}}
        )

        self.assertEqual(result["error"]["code"], "MODEL_ASSET_MISSING")
        mock_check_server.assert_not_called()

    @patch("handler.check_server", return_value=False)
    @patch("handler._check_video_model_assets", return_value=(True, None))
    def test_handler_preflights_hunyuan_model_by_model_name(
        self, mock_preflight, mock_check_server
    ):
        result = handler.handler(
            {"id": "job-1", "input": {"mode": "hunyuan-t2v", "prompt": "test video"}}
        )

        mock_preflight.assert_called_once_with("hunyuanvideo-1.5")
        mock_check_server.assert_called_once()
        self.assertIn("error", result)

    def test_invalid_json_string_input(self):
        validated_data, error = handler.validate_input("invalid json")

        self.assertIsNone(validated_data)
        self.assertEqual(error["code"], "VALIDATION_ERROR")
        self.assertEqual(error["message"], "Invalid JSON format in input")

    def test_empty_input(self):
        validated_data, error = handler.validate_input(None)

        self.assertIsNone(validated_data)
        self.assertEqual(error["code"], "VALIDATION_ERROR")
        self.assertEqual(error["message"], "Please provide input")

    @patch("handler.requests.get")
    def test_check_server_server_up(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = handler.check_server("http://127.0.0.1:8188", 1, 1)

        self.assertTrue(result)

    @patch("handler.requests.get")
    def test_check_server_server_down(self, mock_get):
        mock_get.side_effect = handler.requests.RequestException()

        result = handler.check_server("http://127.0.0.1:8188", 1, 1)

        self.assertFalse(result)

    @patch("handler.requests.post")
    def test_queue_workflow(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"prompt_id": "123"}
        mock_post.return_value = mock_response

        result = handler.queue_workflow({"prompt": "test"}, "client-123")

        self.assertEqual(result, {"prompt_id": "123"})
        payload = json.loads(mock_post.call_args.kwargs["data"])
        self.assertEqual(payload["prompt"], {"prompt": "test"})
        self.assertEqual(payload["client_id"], "client-123")

    @patch("handler.requests.get")
    def test_get_history(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"key": "value"}
        mock_get.return_value = mock_response

        result = handler.get_history("123")

        self.assertEqual(result, {"key": "value"})
        mock_get.assert_called_with("http://127.0.0.1:8188/history/123", timeout=30)

    @patch("handler.requests.post")
    def test_upload_images_successful(self, mock_post):
        mock_response = unittest.mock.Mock()
        mock_response.status_code = 200
        mock_response.text = "Successfully uploaded"
        mock_post.return_value = mock_response

        test_image_data = base64.b64encode(b"Test Image Data").decode("utf-8")
        images = [{"name": "test_image.png", "image": test_image_data}]

        responses = handler.upload_images(images)

        self.assertEqual(len(responses), 3)
        self.assertEqual(responses["status"], "success")

    @patch("handler.requests.post")
    def test_upload_images_failed(self, mock_post):
        mock_response = unittest.mock.Mock()
        mock_response.status_code = 400
        mock_response.text = "Error uploading"
        mock_response.raise_for_status.side_effect = handler.requests.HTTPError(
            "bad request"
        )
        mock_post.return_value = mock_response

        test_image_data = base64.b64encode(b"Test Image Data").decode("utf-8")
        images = [{"name": "test_image.png", "image": test_image_data}]

        responses = handler.upload_images(images)

        self.assertEqual(len(responses), 3)
        self.assertEqual(responses["status"], "error")

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
        self.assertEqual(
            result["image"],
            base64.b64encode(b"image-bytes").decode("utf-8"),
        )
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

    def test_build_s3_key_defaults_to_video_prefix(self):
        self.assertEqual(
            handler._build_s3_key("job-1", "../out.mp4"),
            "video/job-1/out.mp4",
        )

    def test_normalize_s3_endpoint_uses_path_bucket_for_legacy_config(self):
        endpoint, bucket = handler._normalize_s3_endpoint_and_bucket(
            "https://account.r2.cloudflarestorage.com/runpod-serverless"
        )

        self.assertEqual(endpoint, "https://account.r2.cloudflarestorage.com")
        self.assertEqual(bucket, "runpod-serverless")

    @patch("handler._get_s3_client")
    def test_upload_artifact_to_s3_uses_configured_bucket_and_video_prefix(
        self, mock_get_client
    ):
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = (
            "https://bucket.example.com/video/job-1/out.mp4"
        )
        mock_get_client.return_value = mock_client

        with patch.dict(
            os.environ,
            {
                "BUCKET_ENDPOINT_URL": "https://account.r2.cloudflarestorage.com",
                "BUCKET_ACCESS_KEY_ID": "access",
                "BUCKET_SECRET_ACCESS_KEY": "secret",
                "BUCKET_NAME": "runpod-serverless",
            },
        ):
            url = handler._upload_artifact_to_s3("job-1", "out.mp4", b"video-bytes")

        mock_get_client.assert_called_once_with(
            "https://account.r2.cloudflarestorage.com"
        )
        mock_client.put_object.assert_called_once_with(
            Bucket="runpod-serverless",
            Key="video/job-1/out.mp4",
            Body=b"video-bytes",
            ContentType="video/mp4",
        )
        mock_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "runpod-serverless", "Key": "video/job-1/out.mp4"},
            ExpiresIn=604800,
        )
        self.assertEqual(url, "https://bucket.example.com/video/job-1/out.mp4")

    @patch("handler.get_image_data", return_value=b"video-bytes")
    @patch(
        "handler._upload_artifact_to_s3",
        return_value="https://bucket.example.com/out.mp4",
    )
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
    @patch(
        "handler._upload_artifact_to_s3",
        return_value="https://bucket.example.com/out.mp4",
    )
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

    @patch("handler.get_image_data", return_value=b"video-bytes")
    @patch(
        "handler._upload_artifact_to_s3",
        return_value="https://bucket.example.com/out.mp4",
    )
    def test_collect_video_outputs_from_history_animated(self, mock_upload, mock_get):
        history_outputs = {
            "61": {
                "animated": [
                    {
                        "filename": "out.mp4",
                        "subfolder": "video",
                        "type": "output",
                    }
                ],
                "images": [
                    {
                        "filename": "out.png",
                        "subfolder": "video",
                        "type": "output",
                    }
                ],
            }
        }

        videos, errors = handler._collect_video_outputs("job-1", history_outputs)

        self.assertEqual(errors, [])
        self.assertEqual(videos[0]["filename"], "out.mp4")
        mock_get.assert_called_once_with("out.mp4", "video", "output")

    @patch("handler.get_image_data", return_value=b"video-bytes")
    @patch(
        "handler._upload_artifact_to_s3",
        return_value="https://bucket.example.com/out.mp4",
    )
    def test_collect_video_outputs_skips_animated_boolean_flag(
        self, mock_upload, mock_get
    ):
        history_outputs = {
            "61": {
                "animated": [True],
                "images": [
                    {
                        "filename": "out.mp4",
                        "subfolder": "video",
                        "type": "output",
                    }
                ],
            }
        }

        videos, errors = handler._collect_video_outputs("job-1", history_outputs)

        self.assertEqual(errors, [])
        self.assertEqual(videos[0]["filename"], "out.mp4")
        mock_get.assert_called_once_with("out.mp4", "video", "output")

    def test_history_outputs_key_summary_includes_nested_output_keys_only(self):
        summary = handler._history_outputs_key_summary(
            {
                "61": {
                    "animated": [
                        {
                            "filename": "out.mp4",
                            "subfolder": "video",
                            "type": "output",
                            "nested": {"foo": "bar"},
                        }
                    ],
                    "images": [{"filename": "thumb.png", "type": "output"}],
                }
            }
        )

        node_summary = summary["61"]
        self.assertEqual(node_summary["keys"], ["animated", "images"])
        animated_summary = node_summary["children"]["animated"]
        self.assertEqual(animated_summary["type"], "list")
        self.assertEqual(animated_summary["count"], 1)
        item_summary = animated_summary["items"][0]
        self.assertEqual(
            item_summary["keys"],
            ["filename", "nested", "subfolder", "type"],
        )
        self.assertEqual(
            item_summary["media_fields"],
            {
                "filename": "out.mp4",
                "subfolder": "video",
                "type": "output",
            },
        )
        self.assertEqual(
            item_summary["children"]["nested"]["keys"],
            ["foo"],
        )

    @patch("handler.get_image_data", return_value=b"video-bytes")
    @patch(
        "handler._upload_artifact_to_s3",
        return_value="https://bucket.example.com/out.mp4",
    )
    def test_collect_video_outputs_from_history_images_with_video_extension(
        self, mock_upload, mock_get
    ):
        history_outputs = {
            "61": {
                "images": [
                    {
                        "filename": "out.mp4",
                        "subfolder": "video",
                        "type": "output",
                    },
                    {
                        "filename": "thumb.png",
                        "subfolder": "video",
                        "type": "output",
                    },
                ]
            }
        }

        videos, errors = handler._collect_video_outputs("job-1", history_outputs)

        self.assertEqual(errors, [])
        self.assertEqual(videos[0]["filename"], "out.mp4")
        mock_get.assert_called_once_with("out.mp4", "video", "output")

    @patch(
        "handler._upload_artifact_to_s3",
        return_value="https://bucket.example.com/job-1_wan22_t2v_00001.mp4",
    )
    def test_collect_recent_video_file_when_savevideo_history_has_no_video_keys(
        self, mock_upload
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = os.path.join(tmpdir, "output")
            video_dir = os.path.join(output_dir, "video")
            os.makedirs(video_dir)
            video_path = os.path.join(video_dir, "job-1_wan22_t2v_00001.mp4")
            with open(video_path, "wb") as video_file:
                video_file.write(b"video-bytes")

            with patch.dict(os.environ, {"COMFY_OUTPUT_DIR": output_dir}):
                videos, errors = handler._collect_recent_video_files(
                    "job-1",
                    since_epoch=time.time() - 60,
                    filename_prefix="video/job-1_wan22_t2v",
                )

        self.assertEqual(errors, [])
        self.assertEqual(
            videos,
            [
                {
                    "filename": "job-1_wan22_t2v_00001.mp4",
                    "type": "s3_url",
                    "data": "https://bucket.example.com/job-1_wan22_t2v_00001.mp4",
                }
            ],
        )
        mock_upload.assert_called_once_with(
            "job-1", "job-1_wan22_t2v_00001.mp4", b"video-bytes"
        )

    @patch(
        "handler._upload_artifact_to_s3",
        return_value="https://bucket.example.com/job-1_wan22_t2v_00001.mp4",
    )
    def test_collect_recent_video_file_prefers_comfyui_output_when_comfy_root_is_volume(
        self, mock_upload
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            comfy_output = os.path.join(tmpdir, "comfyui-output")
            volume_root = os.path.join(tmpdir, "runpod-volume")
            os.makedirs(comfy_output)
            os.makedirs(volume_root)
            video_path = os.path.join(comfy_output, "job-1_wan22_t2v_00001.mp4")
            with open(video_path, "wb") as video_file:
                video_file.write(b"video-bytes")

            with patch.dict(os.environ, {"COMFY_ROOT": volume_root}, clear=False):
                with patch(
                    "handler._comfy_output_dirs",
                    return_value=[comfy_output, os.path.join(volume_root, "output")],
                ):
                    videos, errors = handler._collect_recent_video_files(
                        "job-1",
                        since_epoch=time.time() - 60,
                        filename_prefix="video/job-1_wan22_t2v",
                    )

        self.assertEqual(errors, [])
        self.assertEqual(videos[0]["filename"], "job-1_wan22_t2v_00001.mp4")
