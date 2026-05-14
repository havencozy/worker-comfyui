import base64
import json
import os
import sys
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
    rp_upload_module = types.ModuleType("runpod.serverless.utils.rp_upload")

    serverless_module.start = Mock()
    rp_upload_module.upload_image = Mock(return_value="simulated_uploaded/image.png")
    utils_module.rp_upload = rp_upload_module
    serverless_module.utils = utils_module
    runpod_module.serverless = serverless_module

    sys.modules.setdefault("runpod", runpod_module)
    sys.modules.setdefault("runpod.serverless", serverless_module)
    sys.modules.setdefault("runpod.serverless.utils", utils_module)
    sys.modules.setdefault("runpod.serverless.utils.rp_upload", rp_upload_module)


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
