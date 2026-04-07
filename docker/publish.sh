#!/bin/sh

#set -x
#docker images

set -e
SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" >/dev/null 2>&1 && pwd)
set -a
. ${SCRIPT_DIR}/../.env
set +a

docker push "$BASE_URL"/create_bsim_db:$VERSION
docker push "$BASE_URL"/create_bsim_db:latest

docker push "$BASE_URL"/elastic_bsim:$VERSION
docker push "$BASE_URL"/elastic_bsim:latest

docker push "$BASE_URL"/ghidra-bsim-postgres:$VERSION
docker push "$BASE_URL"/ghidra-bsim-postgres:latest

docker push "$BASE_URL"/ghidraheadless-python3:$VERSION
docker push "$BASE_URL"/ghidraheadless-python3:latest

docker push "$BASE_URL"/ghidraheadless:$VERSION
docker push "$BASE_URL"/ghidraheadless:latest

docker push "$BASE_URL"/sighthouse-pipeline:$VERSION
docker push "$BASE_URL"/sighthouse-pipeline:latest

docker push "$BASE_URL"/sighthouse:$VERSION
docker push "$BASE_URL"/sighthouse:latest

docker push "$BASE_URL"/sighthouse-frontend:$VERSION
docker push "$BASE_URL"/sighthouse-frontend:latest
