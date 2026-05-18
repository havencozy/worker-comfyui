#!/usr/bin/env bash

# Start SSH server if PUBLIC_KEY is set (enables remote access and dev-sync.sh)
if [ -n "$PUBLIC_KEY" ]; then
    mkdir -p ~/.ssh
    echo "$PUBLIC_KEY" > ~/.ssh/authorized_keys
    chmod 700 ~/.ssh
    chmod 600 ~/.ssh/authorized_keys

    # Generate host keys if they don't exist (removed during image build for security)
    for key_type in rsa ecdsa ed25519; do
        key_file="/etc/ssh/ssh_host_${key_type}_key"
        if [ ! -f "$key_file" ]; then
            ssh-keygen -t "$key_type" -f "$key_file" -q -N ''
        fi
    done

    service ssh start && echo "worker-comfyui: SSH server started" || echo "worker-comfyui: SSH server could not be started" >&2
fi

# Use libtcmalloc for better memory management
TCMALLOC="$(ldconfig -p | grep -Po "libtcmalloc.so.\d" | head -n 1)"
export LD_PRELOAD="${TCMALLOC}"

COMFY_PYTHON="${COMFY_PYTHON:-/comfyui/.venv/bin/python}"
HANDLER_PYTHON="${HANDLER_PYTHON:-/opt/venv/bin/python}"

if [ ! -x "$COMFY_PYTHON" ]; then
    echo "worker-comfyui: ComfyUI Python not found or not executable: $COMFY_PYTHON" >&2
    exit 1
fi

if [ ! -x "$HANDLER_PYTHON" ]; then
    echo "worker-comfyui: Handler Python not found or not executable: $HANDLER_PYTHON" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# GPU pre-flight check
# Verify that the GPU is accessible before starting ComfyUI. If PyTorch
# cannot initialize CUDA the worker will never be able to process jobs,
# so we fail fast with an actionable error message.
# ---------------------------------------------------------------------------
echo "worker-comfyui: Checking GPU availability..."
if [ "${SKIP_GPU_CHECK:-false}" = "true" ]; then
    echo "worker-comfyui: GPU check skipped because SKIP_GPU_CHECK=true"
elif ! GPU_CHECK=$("$COMFY_PYTHON" -c "
import torch
try:
    torch.cuda.init()
    name = torch.cuda.get_device_name(0)
    print(f'OK: {name}')
except Exception as e:
    print(f'FAIL: {e}')
    exit(1)
" 2>&1); then
    echo "worker-comfyui: GPU is not available. PyTorch CUDA init failed:"
    echo "worker-comfyui: $GPU_CHECK"
    echo "worker-comfyui: This usually means the GPU on this machine is not properly initialized."
    echo "worker-comfyui: Please contact RunPod support and report this machine."
    exit 1
else
    echo "worker-comfyui: GPU available — $GPU_CHECK"
fi

# Ensure ComfyUI-Manager runs in offline network mode inside the container
comfy-manager-set-mode offline || echo "worker-comfyui - Could not set ComfyUI-Manager network_mode" >&2

echo "worker-comfyui: Starting ComfyUI"

# Allow operators to tweak verbosity; default is INFO for production video runs.
: "${COMFY_LOG_LEVEL:=INFO}"

# PID file used by the handler to detect if ComfyUI is still running
COMFY_PID_FILE="/tmp/comfyui.pid"

start_comfyui() {
    local -a comfy_args
    comfy_args=("$@")
    comfy_args+=("--disable-auto-launch" "--disable-metadata" "--verbose" "${COMFY_LOG_LEVEL}" "--log-stdout")

    if [ -n "${COMFY_EXTRA_ARGS:-}" ]; then
        # Split operator-provided flags such as:
        # COMFY_EXTRA_ARGS="--cuda-malloc --use-split-cross-attention"
        local -a extra_args
        read -r -a extra_args <<< "${COMFY_EXTRA_ARGS}"
        comfy_args+=("${extra_args[@]}")
        echo "worker-comfyui: Applying COMFY_EXTRA_ARGS: ${COMFY_EXTRA_ARGS}"
    fi

    "$COMFY_PYTHON" -u /comfyui/main.py "${comfy_args[@]}" &
    echo $! > "$COMFY_PID_FILE"
}

# Serve the API and don't shutdown the container
if [ "$SERVE_API_LOCALLY" == "true" ]; then
    start_comfyui --listen

    echo "worker-comfyui: Starting RunPod Handler"
    "$HANDLER_PYTHON" -u /handler.py --rp_serve_api --rp_api_host=0.0.0.0
else
    start_comfyui

    echo "worker-comfyui: Starting RunPod Handler"
    "$HANDLER_PYTHON" -u /handler.py
fi
