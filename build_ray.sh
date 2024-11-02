#!/bin/bash
set -ex

# Ray doesn't publish combiend images because idk.
RAY_VERSION=2.38.0-py311
RAY_IMAGE=holdenk/ray:${RAY_VERSION}
RAY_IMAGE=holdenk/ray:${RAY_VERSION}
COMBINED_IMAGE=holdenk/fhi-ray:${FHI_VERSION}
export RAY_VERSION
docker pull "${RAY_IMAGE}" || docker buildx build --platform=linux/amd64,linux/arm64 -t "${RAY_IMAGE}" . -f RayDockerfile --push --build-arg RAY_VERSION=${RAY_VERSION}
docker pull "${COMBINED_IMAGE}" || docker buildx build --platform=linux/amd64,linux/arm64 -t "${COMBINED_IMAGE}" . -f CombinedDockerfile --push --build-arg RAY_VERSION=${RAY_VERSION}
