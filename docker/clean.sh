#!/bin/sh

SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" >/dev/null 2>&1 && pwd)

echo "Cleaning docker build files"
rm -rf $SCRIPT_DIR/docker-sighthouse/build
