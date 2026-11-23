#!/usr/bin/env bash
# Roda os testes e gera dist/*.deb e dist/*.rpm (funciona no Mint e no Fedora).
set -euo pipefail
cd "$(dirname "$0")"
python3 tests/test_core.py
python3 packaging/build_packages.py all
python3 tests/verify_rpm.py dist/*.rpm >/dev/null && echo "RPM: estrutura OK"
ls -lh dist/
