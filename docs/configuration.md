# Configuration

This document outlines the environment variables available for configuring the `worker-comfyui`.

## General Configuration

| Environment Variable | Description                                                                                                                                                                                                                  | Default |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| `REFRESH_WORKER`     | When `true`, the worker pod will stop after each completed job to ensure a clean state for the next job. See the [RunPod documentation](https://docs.runpod.io/docs/handler-additional-controls#refresh-worker) for details. | `false` |
| `SERVE_API_LOCALLY`  | When `true`, enables a local HTTP server simulating the RunPod environment for development and testing. See the [Development Guide](development.md#local-api) for more details.                                              | `false` |
| `COMFY_ORG_API_KEY`  | Comfy.org API key to enable ComfyUI API Nodes. If set, it is sent with each workflow; clients can override per request via `input.comfy_org_api_key` or `input.api_key_comfy_org`. | – |
| `COMFY_EXTRA_ARGS`   | Optional extra flags appended to the ComfyUI launch command. Useful for GPU-specific tuning such as `--cuda-malloc --use-split-cross-attention`. Use one variable change at a time when benchmarking. | – |
| `WAN22_T2V_WORKFLOW_PATH` | Override path for the Wan2.2 14B T2V API-format workflow. | `/workflows/wan2_2_14b_t2v.json` |
| `WAN22_I2V_WORKFLOW_PATH` | Override path for the Wan2.2 14B I2V API-format workflow. | `/workflows/wan2_2_14b_i2v.json` |
| `WAN22_R2V_WORKFLOW_PATH` | Override path for the Wan2.2 14B FLF2V API-format workflow. | `/workflows/wan2_2_14b_flf2v.json` |
| `WAN22_MODEL_ROOTS` | Optional `:`-separated model roots checked before each job. Defaults to network volume first, then local ComfyUI models. | `/runpod-volume/models:/comfyui/models` |

When building with `--build-arg MODEL_TYPE=none`, the image does not download Wan2.2 models. Put the required model files on the mounted network volume under `/runpod-volume/models/...`; the handler preflight will fail fast with `MODEL_ASSET_MISSING` if a required file is not visible.

## Logging Configuration

| Environment Variable   | Description                                                                                                                                                      | Default |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| `COMFY_LOG_LEVEL`      | Controls ComfyUI's internal logging verbosity. Options: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. Use `DEBUG` for troubleshooting, `INFO` for production. | `INFO` |
| `NETWORK_VOLUME_DEBUG` | Enable detailed network volume diagnostics in worker logs. Useful for debugging model path issues. See [Network Volumes & Model Paths](network-volumes.md).      | `false` |

## Debugging Configuration

| Environment Variable           | Description                                                                                                            | Default |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------- | ------- |
| `WEBSOCKET_RECONNECT_ATTEMPTS` | Number of websocket reconnection attempts when connection drops during job execution.                                  | `5`     |
| `WEBSOCKET_RECONNECT_DELAY_S`  | Delay in seconds between websocket reconnection attempts.                                                              | `3`     |
| `WEBSOCKET_TRACE`              | Enable low-level websocket frame tracing for protocol debugging. Set to `true` only when diagnosing connection issues. | `false` |

## AWS S3 Upload Configuration

Configure these variables so the worker can upload generated videos directly to an AWS S3 bucket. Wan2.2 video deployments require S3-compatible upload configuration. Video artifacts are not returned inline as base64 in production.

- **Prerequisites:**
  - An AWS S3 bucket in your desired region.
  - An AWS IAM user with programmatic access (Access Key ID and Secret Access Key).
  - Permissions attached to the IAM user allowing `s3:PutObject` (and potentially `s3:PutObjectAcl` if you need specific ACLs) on the target bucket.

| Environment Variable       | Description                                                                                                                             | Example                                                    |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| `BUCKET_ENDPOINT_URL`      | The full endpoint URL of your S3 bucket. **Must be set to enable S3 upload.**                                                           | `https://<your-bucket-name>.s3.<aws-region>.amazonaws.com` |
| `BUCKET_ACCESS_KEY_ID`     | Your AWS access key ID associated with the IAM user that has write permissions to the bucket. Required if `BUCKET_ENDPOINT_URL` is set. | `AKIAIOSFODNN7EXAMPLE`                                     |
| `BUCKET_SECRET_ACCESS_KEY` | Your AWS secret access key associated with the IAM user. Required if `BUCKET_ENDPOINT_URL` is set.                                      | `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY`                 |

**Note:** Upload uses the `runpod` Python library helper `rp_upload.upload_image`, which handles creating a unique path within the bucket based on the `job_id`.

### Example S3 Response

If the S3 environment variables (`BUCKET_ENDPOINT_URL`, `BUCKET_ACCESS_KEY_ID`, `BUCKET_SECRET_ACCESS_KEY`) are correctly configured, a successful video job response will look similar to this:

```json
{
  "id": "sync-uuid-string",
  "status": "COMPLETED",
  "output": {
    "videos": [
      {
        "filename": "wan22_t2v_00001.mp4",
        "type": "s3_url",
        "data": "https://your-bucket-name.s3.your-region.amazonaws.com/sync-uuid-string/wan22_t2v_00001.mp4"
      }
    ],
    "meta": {
      "mode": "t2v",
      "model": "wan2.2-14b",
      "fps": 24,
      "duration_sec": 5,
      "num_frames": 120,
      "width": 1280,
      "height": 720,
      "warnings": []
    }
  },
  "delayTime": 123,
  "executionTime": 4567
}
```

The `data` field contains the presigned URL to the uploaded video file in your S3 bucket. The path usually includes the job ID.
