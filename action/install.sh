#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
# Install a release of actuator-lint on a GitHub Actions runner: the Python
# package in a virtual environment and the engine for the runner's platform,
# both under $RUNNER_TEMP. The steps are those of the README.
set -euo pipefail

VERSION="${ACTUATOR_LINT_VERSION#v}"

case "${VERSION}" in
'' | *[!0-9a-z.]*)
	echo "::error::version '${ACTUATOR_LINT_VERSION}' is not a release of actuator-lint such as 0.4.0"
	exit 2
	;;
esac

case "${RUNNER_OS}-${RUNNER_ARCH}" in
Linux-X64) PLATFORM=linux-x86_64 ;;
Linux-ARM64) PLATFORM=linux-arm64 ;;
macOS-ARM64) PLATFORM=macos-arm64 ;;
*)
	echo "::error::actuator-lint has no prebuilt engine for ${RUNNER_OS} ${RUNNER_ARCH}"
	exit 2
	;;
esac

if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
	echo "::error::actuator-lint needs Python 3.11 or newer, the runner has $(python3 --version 2>&1)"
	exit 2
fi

HOME_DIR="${RUNNER_TEMP}/actuator-lint"
BASE="https://github.com/Abtektas/actuator-lint/releases/download/v${VERSION}"
mkdir -p "${HOME_DIR}/download"
cd "${HOME_DIR}/download"

python3 -m venv "${HOME_DIR}/venv"
"${HOME_DIR}/venv/bin/pip" install --quiet --disable-pip-version-check \
	"${BASE}/actuator_lint-${VERSION}-py3-none-any.whl"

curl -fsSLO "${BASE}/SHA256SUMS"
NAME="$(grep -o "actuator_lint_engine-.*-${PLATFORM}" SHA256SUMS)"
curl -fsSLO "${BASE}/${NAME}.tar.gz"
shasum -a 256 --ignore-missing -c SHA256SUMS
# the file was built by the release workflow of the actuator-lint repository
gh attestation verify "${NAME}.tar.gz" -R Abtektas/actuator-lint > /dev/null
tar -xzf "${NAME}.tar.gz"
mkdir -p "${HOME_DIR}/engine"
cp "${NAME}/actuator_lint_engine" "${HOME_DIR}/engine/"

echo "${HOME_DIR}/venv/bin" >> "${GITHUB_PATH}"
echo "ACTUATOR_LINT_ENGINE=${HOME_DIR}/engine/actuator_lint_engine" >> "${GITHUB_ENV}"
ACTUATOR_LINT_ENGINE="${HOME_DIR}/engine/actuator_lint_engine" "${HOME_DIR}/venv/bin/actuator-lint" engines
