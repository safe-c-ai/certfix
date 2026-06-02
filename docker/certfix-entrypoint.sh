#!/bin/sh
set -eu

case "${1:-}" in
  certfix|certfix-docker|sh|bash|python|python3)
    exec "$@"
    ;;
  "")
    exec certfix --help
    ;;
  *)
    exec certfix "$@"
    ;;
esac
