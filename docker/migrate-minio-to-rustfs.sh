#!/bin/sh
#
# Usage:
#   ./migrate-minio-to-rustfs.sh <path> [bucket ...]
#
# Examples:
#   ./migrate-minio-to-rustfs.sh pipeline/data            # bucket 'uploads'
#   ./migrate-minio-to-rustfs.sh frontend/data frontend   # bucket 'frontend'

set -eu

DATA_DIR="${1:-./data}"
shift 2>/dev/null || true
BUCKETS="${*:-uploads frontend}"
ACCESS="admin"
SECRET="password"
NET="sighthouse-migrate"
MINIO_IMG="minio/minio:RELEASE.2025-04-22T22-12-26Z"
RUSTFS_IMG="rustfs/rustfs:latest"
RC_IMG="rustfs/rc:latest"

if [ ! -d "$DATA_DIR/minio" ]; then
  echo "Failed : '$DATA_DIR/minio' not found" >&2
  exit 1
fi

cleanup() {
  docker rm -f mig-minio mig-rustfs >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup
docker network create "$NET" >/dev/null

docker run -d --name mig-minio --network "$NET" \
  -e MINIO_ROOT_USER="$ACCESS" -e MINIO_ROOT_PASSWORD="$SECRET" \
  -v "$(cd "$DATA_DIR/minio" && pwd):/data" \
  "$MINIO_IMG" server /data >/dev/null

mkdir -p "$DATA_DIR/rustfs"
docker run -d --name mig-rustfs --network "$NET" \
  --user 1000:1000 \
  -e RUSTFS_ACCESS_KEY="$ACCESS" -e RUSTFS_SECRET_KEY="$SECRET" \
  -e RUSTFS_VOLUMES=/data -e RUSTFS_ADDRESS=:9000 \
  -v "$(cd "$DATA_DIR/rustfs" && pwd):/data" \
  "$RUSTFS_IMG" >/dev/null

set +e
docker run --rm --network "$NET" --entrypoint /bin/sh "$RC_IMG" -c "
  set -e
  until rc alias set src http://mig-minio:9000  $ACCESS $SECRET; do echo waiting minio; sleep 2; done
  until rc alias set dst http://mig-rustfs:9000 $ACCESS $SECRET; do echo waiting rustfs; sleep 2; done
  fail=0
  for b in $BUCKETS; do
    if ! rc ls src/\$b >/dev/null 2>&1; then
      continue
    fi
    rc mb dst/\$b || true
    echo \"== mirror \$b ==\"
    if ! rc mirror src/\$b/ dst/\$b/; then
      fail=1
      continue
    fi
    rc anonymous set download dst/\$b || true
    src_n=\$(rc ls --recursive src/\$b/ 2>/dev/null | grep -c .)
    dst_n=\$(rc ls --recursive dst/\$b/ 2>/dev/null | grep -c .)
    if [ \"\$src_n\" -ne \"\$dst_n\" ]; then
      fail=1
    fi
  done
  exit \$fail
"
rc=$?
set -e

if [ "$rc" -ne 0 ]; then
  exit "$rc"
fi
