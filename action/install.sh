#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
# Install a release of px4-ca-lint on a GitHub Actions runner: the Python
# package in a virtual environment and the engine for the runner's platform,
# both under $RUNNER_TEMP. The steps are those of the README.
set -euo pipefail

VERSION="${PX4_CA_LINT_VERSION#v}"

case "${VERSION}" in
'' | *[!0-9a-z.]*)
	echo "::error::version '${PX4_CA_LINT_VERSION}' is not a release of px4-ca-lint such as 0.4.0"
	exit 2
	;;
esac

case "${RUNNER_OS}-${RUNNER_ARCH}" in
Linux-X64) PLATFORM=linux-x86_64 ;;
Linux-ARM64) PLATFORM=linux-arm64 ;;
macOS-ARM64) PLATFORM=macos-arm64 ;;
*)
	echo "::error::px4-ca-lint has no prebuilt engine for ${RUNNER_OS} ${RUNNER_ARCH}"
	exit 2
	;;
esac

if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
	echo "::error::px4-ca-lint needs Python 3.11 or newer, the runner has $(python3 --version 2>&1)"
	exit 2
fi

HOME_DIR="${RUNNER_TEMP}/px4-ca-lint"
BASE="https://github.com/Abtektas/px4-ca-lint/releases/download/v${VERSION}"
mkdir -p "${HOME_DIR}/download"
cd "${HOME_DIR}/download"

python3 -m venv "${HOME_DIR}/venv"
"${HOME_DIR}/venv/bin/pip" install --quiet --disable-pip-version-check \
	"${BASE}/px4_ca_lint-${VERSION}-py3-none-any.whl"

curl -fsSLO "${BASE}/SHA256SUMS"
NAME="$(grep -o "px4_ca_engine-.*-${PLATFORM}" SHA256SUMS)"
curl -fsSLO "${BASE}/${NAME}.tar.gz"
shasum -a 256 --ignore-missing -c SHA256SUMS
# the file was built by the release workflow of the px4-ca-lint repository
gh attestation verify "${NAME}.tar.gz" -R Abtektas/px4-ca-lint > /dev/null
tar -xzf "${NAME}.tar.gz"
mkdir -p "${HOME_DIR}/engine"
cp "${NAME}/px4_ca_engine" "${HOME_DIR}/engine/"

echo "${HOME_DIR}/venv/bin" >> "${GITHUB_PATH}"
echo "PX4_CA_ENGINE=${HOME_DIR}/engine/px4_ca_engine" >> "${GITHUB_ENV}"
PX4_CA_ENGINE="${HOME_DIR}/engine/px4_ca_engine" "${HOME_DIR}/venv/bin/px4-ca-lint" engines
