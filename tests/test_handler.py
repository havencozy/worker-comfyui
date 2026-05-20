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
    def test_valid_t2i_input_builds_workflow_from_template(self):
        input_data = {
            "mode": "t2i",
            "prompt": "a red fox in a studio portrait",
            "aspect_ratio": "16:9",
            "count": 2,
            "options": {
                "steps": 12,
                "seed": 42,
                "cfg": 3.5,
                "sampler_name": "ddim",
            },
        }

        validated_data, error = handler.validate_input(input_data)

        self.assertIsNone(error)
        workflow = validated_data["workflow"]
        self.assertIsNone(validated_data["images"])
        self.assertEqual(workflow["6"]["inputs"]["text"], input_data["prompt"])
        self.assertEqual(validated_data["selected_model"], "flux2-klein-t2i")
        self.assertEqual(
            workflow["12"]["inputs"]["unet_name"],
            "flux-2-klein-9b-fp8.safetensors",
        )
        self.assertEqual(
            workflow["38"]["inputs"]["clip_name"],
            "qwen_3_8b_fp8mixed.safetensors",
        )
        self.assertEqual(workflow["47"]["inputs"]["width"], 1344)
        self.assertEqual(workflow["47"]["inputs"]["height"], 768)
        self.assertEqual(workflow["47"]["inputs"]["batch_size"], 2)
        self.assertEqual(workflow["48"]["inputs"]["steps"], 12)
        self.assertEqual(workflow["25"]["inputs"]["noise_seed"], 42)
        self.assertEqual(workflow["26"]["inputs"]["guidance"], 3.5)
        self.assertEqual(workflow["16"]["inputs"]["sampler_name"], "ddim")

    def test_t2i_flux2_dev_model_request_uses_klein_t2i_preset(self):
        input_data = {
            "mode": "t2i",
            "model": "flux2-dev",
            "prompt": "a clean product render",
        }

        validated_data, error = handler.validate_input(input_data)

        self.assertIsNone(error)
        workflow = validated_data["workflow"]
        self.assertEqual(validated_data["selected_model"], "flux2-klein-t2i")
        self.assertEqual(
            workflow["12"]["inputs"]["unet_name"],
            "flux-2-klein-9b-fp8.safetensors",
        )
        self.assertEqual(
            workflow["38"]["inputs"]["clip_name"],
            "qwen_3_8b_fp8mixed.safetensors",
        )

    def test_single_image_i2i_is_disabled_until_replacement_workflow(self):
        input_data = {
            "mode": "i2i",
            "prompt": "preserve identity with cinematic color",
            "image": "data:image/png;base64,ZmFrZQ==",
            "image_name": "portrait.png",
            "count": 3,
        }

        validated_data, error = handler.validate_input(input_data)

        self.assertIsNone(validated_data)
        self.assertEqual(
            error,
            "Single-image i2i workflow is not configured; send 2-5 images for multi-reference i2i",
        )

    def test_single_image_images_array_is_disabled_until_replacement_workflow(self):
        input_data = {
            "mode": "i2i",
            "prompt": "enhance details",
            "images": [{"name": "input.png", "image": "ZmFrZQ=="}],
        }

        validated_data, error = handler.validate_input(input_data)

        self.assertEqual(
            error,
            "Single-image i2i workflow is not configured; send 2-5 images for multi-reference i2i",
        )
        self.assertIsNone(validated_data)

    def test_valid_i2i_input_with_multiple_images_uses_multi_reference_workflow(self):
        input_data = {
            "mode": "i2i",
            "prompt": "make the monkey ride the bicycle",
            "images": [
                {"name": "monkey.png", "image": "ZmFrZQ=="},
                {"name": "bicycle.png", "image": "ZmFrZQ=="},
                {"name": "street.png", "image": "ZmFrZQ=="},
            ],
        }

        validated_data, error = handler.validate_input(input_data)

        self.assertIsNone(error)
        workflow = validated_data["workflow"]
        self.assertEqual(validated_data["images"], input_data["images"])
        self.assertEqual(workflow["46"]["inputs"]["image"], "monkey.png")
        self.assertEqual(workflow["56"]["inputs"]["image"], "bicycle.png")
        self.assertEqual(workflow["66"]["inputs"]["image"], "street.png")
        self.assertEqual(
            workflow["38"]["inputs"]["clip_name"],
            "qwen_3_4b.safetensors",
        )
        self.assertEqual(
            workflow["12"]["inputs"]["unet_name"],
            "flux-2-klein-base-4b-fp8.safetensors",
        )
        self.assertNotIn("76", workflow)
        self.assertEqual(workflow["22"]["inputs"]["conditioning"], ["63", 0])

    def test_i2i_rejects_more_than_five_images(self):
        input_data = {
            "mode": "i2i",
            "prompt": "too many references",
            "images": [
                {"name": f"image_{index}.png", "image": "ZmFrZQ=="}
                for index in range(6)
            ],
        }

        validated_data, error = handler.validate_input(input_data)

        self.assertIsNone(validated_data)
        self.assertEqual(error, "i2i supports at most 5 input images")

    def test_multi_i2i_keeps_klein_preset_when_client_sends_flux2_dev_model(self):
        input_data = {
            "mode": "i2i",
            "model": "flux2-dev",
            "prompt": "make the monkey ride the bicycle",
            "images": [
                {"name": "monkey.png", "image": "ZmFrZQ=="},
                {"name": "bicycle.png", "image": "ZmFrZQ=="},
            ],
        }

        validated_data, error = handler.validate_input(input_data)

        self.assertIsNone(error)
        workflow = validated_data["workflow"]
        self.assertEqual(validated_data["selected_model"], "flux2-klein-multi")
        self.assertEqual(
            workflow["38"]["inputs"]["clip_name"],
            "qwen_3_4b.safetensors",
        )
        self.assertEqual(
            workflow["12"]["inputs"]["unet_name"],
            "flux-2-klein-base-4b-fp8.safetensors",
        )

    def test_valid_json_string_input(self):
        input_data = '{"mode": "t2i", "prompt": "a clean product render"}'

        validated_data, error = handler.validate_input(input_data)

        self.assertIsNone(error)
        self.assertEqual(
            validated_data["workflow"]["6"]["inputs"]["text"],
            "a clean product render",
        )

    def test_input_missing_mode(self):
        validated_data, error = handler.validate_input({"prompt": "hello"})

        self.assertIsNone(validated_data)
        self.assertEqual(
            error,
            "Missing or invalid 'mode'. Supported values: 't2i', 'i2i'",
        )

    def test_input_missing_prompt(self):
        validated_data, error = handler.validate_input({"mode": "t2i"})

        self.assertIsNone(validated_data)
        self.assertEqual(error, "Missing 'prompt' parameter")

    def test_i2i_missing_image(self):
        validated_data, error = handler.validate_input(
            {"mode": "i2i", "prompt": "enhance"}
        )

        self.assertIsNone(validated_data)
        self.assertEqual(error, "Missing 'image' (or 'images') parameter for i2i mode")

    def test_i2i_with_invalid_images_structure(self):
        input_data = {
            "mode": "i2i",
            "prompt": "enhance",
            "images": [{"name": "image1.png"}],
        }

        validated_data, error = handler.validate_input(input_data)

        self.assertIsNone(validated_data)
        self.assertEqual(
            error, "'images' must be a list of objects with 'name' and 'image' keys"
        )

    def test_invalid_json_string_input(self):
        validated_data, error = handler.validate_input("invalid json")

        self.assertIsNone(validated_data)
        self.assertEqual(error, "Invalid JSON format in input")

    def test_empty_input(self):
        validated_data, error = handler.validate_input(None)

        self.assertIsNone(validated_data)
        self.assertEqual(error, "Please provide input")

    def test_summarize_job_input_redacts_image_payloads(self):
        summary = handler.summarize_job_input(
            {
                "mode": "i2i",
                "prompt": "make the monkey ride the bicycle",
                "image": "data:image/png;base64,ZmFrZQ==",
                "images": [{"name": "bike.png", "image": "ZmFrZQ=="}],
                "options": {"seed": 123},
            }
        )

        self.assertEqual(summary["mode"], "i2i")
        self.assertEqual(summary["prompt"], "make the monkey ride the bicycle")
        self.assertEqual(summary["image"], {"present": True, "length": 30})
        self.assertEqual(
            summary["images"],
            [{"name": "bike.png", "has_image": True, "image_length": 8}],
        )
        self.assertEqual(summary["options"], {"seed": 123})

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
