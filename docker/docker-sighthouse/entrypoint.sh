#!/bin/bash
# Make the CLI available on PATH.
export PATH="$PATH:/home/user/.local/bin"

exec sighthouse "$@"
