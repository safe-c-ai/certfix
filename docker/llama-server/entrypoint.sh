#!/bin/sh
set -eu

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

if [ -n "${LLAMA_MODEL_PATH:-}" ]; then
  set -- -m "$LLAMA_MODEL_PATH"
else
  set -- -hf "${LLAMA_GGUF_REPO:-${QWEN36_GGUF_REPO:-unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL}}"
fi

exec llama-server \
  "$@" \
  -ngl "${LLAMA_N_GPU_LAYERS:-99}" \
  -c "${LLAMA_CONTEXT_SIZE:-8192}" \
  -fa "${LLAMA_FLASH_ATTN:-on}" \
  -np "${LLAMA_PARALLEL:-1}" \
  --host "${LLAMA_HOST:-0.0.0.0}" \
  --port "${LLAMA_PORT:-8952}" \
  --cache-ram "${LLAMA_CACHE_RAM:-0}" \
  --spec-type "${LLAMA_SPEC_TYPE:-draft-mtp}" \
  --spec-draft-n-max "${LLAMA_SPEC_DRAFT_N_MAX:-2}" \
  --reasoning-budget "${LLAMA_REASONING_BUDGET:-1024}"
