#!/bin/bash
set -ex
package_command=none

if command -v apt-get; then
  package_command="apt-get install -y"
elif command -v brew; then
  package_command="brew install"
fi

install_package() {
  package_name=$1
  echo "${package_name}"
  if [ ${package_command} == "none" ]; then
    printf 'Can not install %s. Please install it manually.\n' ${package_name} >/dev/stderr
    exit 1
  fi
  ${package_command} ${package_name}
}

if [ ! -f "cert.pem" ]; then
  if ! command -v mkcert &> /dev/null; then
    install_package mkcert
  fi

  mkcert -cert-file cert.pem -key-file key.pem localhost 127.0.0.1
fi

pushd fighthealthinsurance/static/js/
npm i || echo "Can't install?"
npm run build
popd

RECAPTCHA_TESTING=true OAUTHLIB_RELAX_TOKEN_SCOPE=1 \
  python manage.py runserver_plus --cert-file cert.pem --key-file key.pem
