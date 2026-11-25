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

# empty: the newest PX4 release the actuator-lint release has an engine for
PX4="${ACTUATOR_LINT_PX4_INPUT:-}"
case "${PX4}" in
'') ;;
v*[!0-9.]* | v | v.* | *..* | *.)
	echo "::error::px4 '${PX4}' is not a PX4 release such as v1.18.0"
	exit 2
	;;
v[0-9]*.[0-9]*.[0-9]*) ;;
*)
	echo "::error::px4 '${PX4}' is not a PX4 release such as v1.18.0"
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
if [ -z "${PX4}" ]; then
	PX4="$(python3 - "${PLATFORM}" <<'EOF'
import re, sys
found = re.findall(r"actuator_lint_engine-(?:px4-)?(v[0-9]+\.[0-9]+\.[0-9]+)-schema[0-9]+-" + re.escape(sys.argv[1]) + r"\b", open("SHA256SUMS").read())
print(max(found, key=lambda v: tuple(int(n) for n in v[1:].split("."))) if found else "")
EOF
)"
fi
NAME="$(grep -o "actuator_lint_engine-.*${PX4}-schema[0-9]*-${PLATFORM}" SHA256SUMS || true)"
if [ -z "${PX4}" ] || [ -z "${NAME}" ]; then
	echo "::error::release ${VERSION} of actuator-lint has no engine for PX4 ${PX4:-(any)} on ${PLATFORM}; it has:"
	grep -o "actuator_lint_engine-[^ ]*" SHA256SUMS | sed 's/\.tar\.gz$//' >&2
	exit 2
fi
curl -fsSLO "${BASE}/${NAME}.tar.gz"
shasum -a 256 --ignore-missing -c SHA256SUMS
# the file was built by the release workflow of the actuator-lint repository
gh attestation verify "${NAME}.tar.gz" -R Abtektas/actuator-lint > /dev/null
tar -xzf "${NAME}.tar.gz"
mkdir -p "${HOME_DIR}/engine"
cp "${NAME}/actuator_lint_engine" "${HOME_DIR}/engine/"

echo "${HOME_DIR}/venv/bin" >> "${GITHUB_PATH}"
echo "ACTUATOR_LINT_ENGINE=${HOME_DIR}/engine/actuator_lint_engine" >> "${GITHUB_ENV}"
# every run then refuses an engine built against another PX4 version
echo "ACTUATOR_LINT_PX4=${PX4}" >> "${GITHUB_ENV}"
ACTUATOR_LINT_ENGINE="${HOME_DIR}/engine/actuator_lint_engine" ACTUATOR_LINT_PX4="${PX4}" "${HOME_DIR}/venv/bin/actuator-lint" engines
