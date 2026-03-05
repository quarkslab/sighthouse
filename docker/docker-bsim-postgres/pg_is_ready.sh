#!/bin/bash

export LD_LIBRARY_PATH=/ghidra/Ghidra/Features/BSim/build/os/linux_x86_64/postgresql/lib
PG_ISREADY=/ghidra/Ghidra/Features/BSim/build/os/linux_x86_64/postgresql/bin/pg_isready

# On some system, docker does not expose a localhost interface, so we use the IP address
LOCALHOST=127.0.0.1

if [[ ! $(${PG_ISREADY} -h ${LOCALHOST} -p 5432) ]]; then
  exit 1
fi
exit 0
