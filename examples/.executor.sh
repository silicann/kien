#!/bin/sh

PYTHONPATH="$(dirname "$(dirname "$0")")" exec /usr/bin/env python3 "$1"
