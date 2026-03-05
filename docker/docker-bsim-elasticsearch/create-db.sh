#!/bin/bash

USER="$1"
PASSWORD="$2"
HOST="$3"
TYPE="$4"
PORT="$5"

if [[ -z ${PASSWORD} ]]; then
  _JAVA_OPTIONS="-Duser.name=${USER}" /ghidra/support/bsim createdatabase ${TYPE}://${HOST}:${PORT}/bsim medium_nosize -u ${USER}
else
  _JAVA_OPTIONS="-Duser.name=${USER}" /ghidra/support/bsim createdatabase ${TYPE}://${HOST}:${PORT}/bsim medium_nosize -u ${USER} <<< ${PASSWORD}
fi
