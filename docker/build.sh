#!/bin/sh

SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" >/dev/null 2>&1 && pwd)
set -a
. ${SCRIPT_DIR}/../.env
set +a
SIGHTHOUSE_DIR="$SCRIPT_DIR/../sighthouse"

set -ex
# Clean build directory before building dockers
$SCRIPT_DIR/clean.sh
# make -C $SIGHTHOUSE_DIR clean
# Build all the dockers
$SCRIPT_DIR/docker-ghidra/build.sh
$SCRIPT_DIR/docker-ghidra-python3/build.sh
# PLEASE DO NOT REMOVE create_db is inside and you can't launch pipeline without this line
$SCRIPT_DIR/docker-bsim-elasticsearch/build.sh
$SCRIPT_DIR/docker-bsim-postgres/build.sh
$SCRIPT_DIR/docker-sighthouse/build.sh
