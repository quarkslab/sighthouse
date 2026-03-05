#!/bin/bash
# Add local bin to PATH
export PATH="$PATH:/home/user/.local/bin"

# First argument: package path to install
PACKAGE_PATH="$1"
shift

# Second argument: package name
PACKAGE_NAME="$1"
shift

# Install the package if PACKAGE_PATH is provided
if [ -n "$PACKAGE_PATH" ]; then
    sighthouse package install "$PACKAGE_PATH"
fi

# Run the analyzer with remaining arguments
echo "sighthouse package run $PACKAGE_NAME $@"
sighthouse package run "$PACKAGE_NAME" "$@"

