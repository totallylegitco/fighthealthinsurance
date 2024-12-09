#!/bin/bash
set -ex

JS_PATH=fighthealthinsurance/static/js

pushd "${JS_PATH}"
npm ls >/dev/null 2>&1
npm_dep_check=$?
popd

pushd "${JS_PATH}"
if [ ${npm_dep_check} != 0 ]; then
	npm i || echo "Can't install?" >/dev/stderr
fi
npm run build
popd
