#!/bin/bash
set -ex

BUILDX_CMD=${BUILDX_CMD:-push}

# Activate the venv if present.
if [ -f ./build_venv/bin/activate ]; then
  source ./build_venv/bin/activate
elif [ -f ./.venv/bin/activate ]; then
  source ./.venv/bin/activate
fi

mypy -p fighthealthinsurance
./manage.py migrate
./manage.py makemigrations
./manage.py migrate
./manage.py validate_templates
./manage.py collectstatic --no-input

pushd ./static/js
npm i
npm run build
popd

FHI_VERSION=v0.9.5b

export FHI_VERSION


# Build ray cluster first so that the cluster can come up before the job that registers the workers
source build_ray.sh
# The raycluster operator doesn't handle upgrades well so delete + recreate instead.
kubectl delete raycluster -n totallylegitco raycluster-kuberay || echo "No raycluster present"
kubectl apply -f k8s/cluster.yaml

# Build the django container
source build_django.sh
kubectl apply -f k8s/deploy.yaml
