#!/bin/sh
# Serve a shader live to a browser and print the address of the page. Usage: stream.sh FRAG WIDTHxHEIGHT

set -eu

FRAG=${1:?usage: stream.sh FRAG WIDTHxHEIGHT}
RES=${2:?usage: stream.sh FRAG WIDTHxHEIGHT}

make -s --no-print-directory -C "$(dirname "$0")" stream FRAG="$(cd "$(dirname "$FRAG")" && pwd)/$(basename "$FRAG")" RES="$RES"
