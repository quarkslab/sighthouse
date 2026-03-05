#!/bin/bash

set -e

chown -R user /home/user/ghidra-data
rm -rf /home/user/ghidra-data/postmaster.pid

/ghidra/support/bsim_ctl start /home/user/ghidra-data
exec "$@"
