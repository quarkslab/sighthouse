#!/bin/sh

#set -x
#docker images

set -e
SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" >/dev/null 2>&1 && pwd)
set -a
. ${SCRIPT_DIR}/../.env
. ${SCRIPT_DIR}/../.version
set +a

docker push "$BASE_URL"/ghidraheadless-python3:1.0.0
docker push "$BASE_URL"/ghidraheadless-python3:latest

docker push "$BASE_URL"/ghidraheadless:1.0.0
docker push "$BASE_URL"/ghidraheadless:latest
