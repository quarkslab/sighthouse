#!/bin/bash

export LD_LIBRARY_PATH=/ghidra/Ghidra/Features/BSim/build/os/linux_x86_64/postgresql/lib
PG_ISREADY=/ghidra/Ghidra/Features/BSim/build/os/linux_x86_64/postgresql/bin/pg_isready

# On some system, docker does not expose a localhost interface, so we use the IP address
LOCALHOST=127.0.0.1

# Start bsim database
/ghidra/support/bsim_ctl start /home/user/ghidra-data

# Wait until ready
while ! ${PG_ISREADY} -h ${LOCALHOST} -p 5432; do
  echo "Waiting for postgresql to be ready"
  sleep 1
done

# Add a user to the database
/ghidra/support/bsim_ctl adduser /home/user/ghidra-data user

# Create our database
#/ghidra/support/bsim createdatabase postgresql://localhost:5432/bsim medium_nosize
