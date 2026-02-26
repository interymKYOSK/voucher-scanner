#!/usr/bin/env bash
cd "$(dirname "$0")"

# Initialise conda (necessary because desktop launchers do not load your shell)
source ~/miniconda3/etc/profile.d/conda.sh

conda activate voucher-scanner
python voucher-scanner.py
