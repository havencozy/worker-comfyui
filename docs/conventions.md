# Introduction

This project (`worker-comfyui`) provides a way to run curated Wan2.2 video generation workflows as a serverless API worker on the [RunPod](https://www.runpod.io/) platform. Its main purpose is to accept simplified `t2v`, `i2v`, and `r2v` payloads and return generated video artifacts as S3 URLs.

It packages ComfyUI into Docker images, manages job handling via the `runpod` SDK, uses websockets for efficient communication with ComfyUI, and facilitates configuration through environment variables.

# Project Conventions and Rules

This document outlines the key operational and structural conventions for the `worker-comfyui` project. While there are no strict code-style rules enforced by linters currently, following these conventions ensures consistency and smooth development/deployment.

## 1. Configuration

- **Environment Variables:** All external configurations (e.g., AWS S3 credentials, RunPod behavior modifications like `REFRESH_WORKER`) **must** be managed via environment variables.
- Refer to the main `README.md` and `docs/configuration.md` for video worker environment variables.

## 2. Docker Usage

- **Container-Centric:** Development, testing, and deployment are heavily reliant on Docker.
- **Platform:** When building Docker images intended for RunPod, **always** use the `--platform linux/amd64` flag to ensure compatibility.
  ```bash
  # Example build command
  docker build --platform linux/amd64 -t my-image:tag .
  ```
- **Development Builds:** For faster development iterations, use `MODEL_TYPE=none` to skip downloading external models:
  ```bash
  docker build --build-arg MODEL_TYPE=none -t runpod/worker-comfyui:dev .
  ```
- **Customization:** Follow the methods in the `README.md` for adding custom models/nodes (Network Volume or Dockerfile edits + snapshots).

## 3. API Interaction

- **Input Structure:** API calls to the `/run` or `/runsync` endpoints must adhere to the JSON structure specified in the `README.md` ("API specification"). The primary key is `input`, containing a simplified Wan2.2 video payload. Raw `input.workflow` payloads are not part of this video worker API.
- **Frame Encoding:** `i2v` and `r2v` inline frame fields (`start_frame`, `end_frame`) must be base64 strings, optionally including a `data:[<mediatype>];base64,` prefix. Remote `r2v` frames use `image_urls`.
- **Workflow Format:** Built-in workflow templates live under `workflows/` and are loaded by mode. To replace a template, export API-format JSON from ComfyUI and save it over the matching Wan2.2 workflow file.
- **Output Structure:** Successful responses contain `output.videos`, a list of video artifact dictionaries with `filename`, `type: "s3_url"`, and `data` containing the uploaded URL. Refer to the `README.md` API examples for the exact structure.
- **Internal Communication:** Job status monitoring uses the ComfyUI websocket API instead of HTTP polling for efficiency.

## 4. Error Handling

- **User-Friendly Errors:** Always surface meaningful error messages to users rather than generic HTTP errors or internal exceptions.
- **ComfyUI Integration:** When ComfyUI returns validation errors, parse the response body to extract detailed error information and present it in a structured, actionable format.
- **Helpful Context:** When possible, provide users with information about available options (e.g., available models, valid parameters) to help them correct their requests.
- **Graceful Fallbacks:** Error handling should degrade gracefully - if detailed error parsing fails, fall back to showing the raw response rather than hiding the error entirely.

## 5. Development Workflow

- **Code Changes:** After modifying handler code, always rebuild the Docker image before testing with `docker-compose`:
  ```bash
  docker-compose down
  docker build --build-arg MODEL_TYPE=none -t runpod/worker-comfyui:dev .
  docker-compose up -d
  ```
- **Debugging:** Use strategic logging/print statements to understand external API responses (like ComfyUI's error formats) before implementing error handling.
- **Testing:** Test error scenarios as thoroughly as success scenarios to ensure good user experience.

## 6. Testing

- **Unit Tests:** Automated tests are located in the `tests/` directory and should be run using `python -m unittest discover`. Add new tests for new functionality or bug fixes.
- **Local Environment:** Use `docker-compose up` for local end-to-end testing. This requires a correctly configured Docker environment with NVIDIA GPU support.

## 7. Dependencies

- **Python:** Manage Python dependencies using `pip` (or `uv`) and the `requirements.txt` file. Keep this file up-to-date.

## 8. Code Style (General Guidance)

- While not enforced by tooling, aim for code clarity and consistency. Follow general Python best practices (e.g., PEP 8).
- Use meaningful variable and function names.
- Add comments where the logic is non-obvious.

### **Model Type Detection**

Models are categorized based on node types using these mappings:

- `UpscaleModelLoader` → `upscale_models`
- `VAELoader` → `vae`
- `UNETLoader`, `UnetLoaderGGUF`, `Hy3DModelLoader` → `diffusion_models`
- `DualCLIPLoader`, `TripleCLIPLoader` → `text_encoders`
- `LoraLoader` → `loras`
- And additional specialized loaders for proper model categorization

## Custom Node Dependencies

When extending the base image with custom nodes, some nodes may require specific dependency versions to function correctly.

### **Known Compatibility Issues**

- **ComfyUI-BrushNet dependency issue:** Requires specific dependency versions: `diffusers>=0.29.0`, `accelerate>=0.29.0,<0.32.0`, and `peft>=0.7.0` to resolve import errors
- **Pattern for fixing:** When encountering import errors from custom nodes, check the dependency chain and ensure compatible versions are installed in the Dockerfile using `uv pip install`
