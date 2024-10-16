#!/bin/bash

JS_PATH=fighthealthinsurance/static/js

python -c 'import configurations' 2>&1>/dev/null
python_dep_check=$?

pushd "${JS_PATH}"
npm ls 2>&1>/dev/null
npm_dep_check=$?
popd

if [ ${python_dep_check} != 0 ]; then
  set +x
  printf 'Python dependencies may be missing. Please install dependencies via:\n' >/dev/stderr
  printf 'pip install -r requirements.txt\n' >/dev/stderr
  exit 1
fi

set -ex

python min_version.py

package_command=''

# Are we sort of connected to the backend?
if kubectl get service -n totallylegitco vllm-health-svc; then
  export HEALTH_BACKEND_PORT=4280
  export HEALTH_BACKEND_HOST=localhost
  kubectl port-forward -n totallylegitco service/vllm-health-svc 4280:80 &
else
  echo 'No connection to kube vllm health svc'
fi
echo "Setup to use $HEALTH_BACKEND_HOST:$HEALTH_BACKEND_PORT"
if command -v apt-get; then
  package_command="apt-get install -y"
elif command -v brew; then
  package_command="brew install"
fi

install_package() {
  package_name=$1
  ${package_command} ${package_name} || sudo ${package_command} ${package_name} || \
    (printf 'Can not install %s. Please install it manually.\n' ${package_name} >/dev/stderr && \
       exit 1)
}

if ! command -v tesseract &> /dev/null; then
  # We need either the tesseract-ocr package OR easyocr
  install_package tesseract-ocr || pip install easyocr
fi


if [ ! -f "cert.pem" ]; then
  if ! command -v mkcert &> /dev/null; then
    install_package mkcert
  fi

  mkcert -cert-file cert.pem -key-file key.pem localhost 127.0.0.1
fi

pushd "${JS_PATH}"
if [ ${npm_dep_check} != 0 ]; then
  npm i || echo "Can't install?" >/dev/stderr
fi
npm run build
popd

python manage.py migrate
python manage.py loaddata initial
python manage.py loaddata followup
python manage.py loaddata plan_source

# Make sure we have an admin user so folks can test the admin view
FIGHT_HEALTH_ADMIN_USER="admin" FIGHT_HEALTH_ADMIN_PASSWORD="admin" python manage.py ensure_adminuser --no-input

RECAPTCHA_TESTING=true OAUTHLIB_RELAX_TOKEN_SCOPE=1 \
  python manage.py runserver_plus --cert-file cert.pem --key-file key.pem $@
