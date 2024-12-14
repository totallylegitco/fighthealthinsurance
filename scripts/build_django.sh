#!/bin/bash
set -ex

BUILDX_CMD=${BUILDX_CMD:-push}

# Build the web app
IMAGE=holdenk/fight-health-insurance:${FHI_VERSION}
(docker pull "${IMAGE}" && sleep 10) || docker buildx build --platform=linux/amd64,linux/arm64 -t "${IMAGE}" -f k8s/Dockerfile "${BUILDX_CMD}"
