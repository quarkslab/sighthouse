#!/bin/bash

set -e

exec "/ghidra/support/analyzeHeadless" "$@" -scriptPath /ghidra_scripts
