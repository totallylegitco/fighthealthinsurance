#!/bin/bash

shellcheck -e SC1091 $(find . -type f -name "*.sh" -not -path "./.tox/*")
