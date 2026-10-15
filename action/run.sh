#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-3-Clause
# Run actuator-lint on the files of the action's input: the text report goes to
# the log, the Markdown report to the job summary. Exits with 1 when a file
# has findings at or above fail-on or cannot be checked.
set -uo pipefail

FAIL_ON="${INPUT_FAIL_ON:-error}"

case "${FAIL_ON}" in
warning | error | never) ;;
*)
	echo "::error::fail-on is '${FAIL_ON}', expected warning, error or never"
	exit 2
	;;
esac

# options are split at spaces, as on a command line without quotes
read -r -a ARGUMENTS <<< "${INPUT_ARGUMENTS:-}"
SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/null}"
[ "${INPUT_SUMMARY:-true}" = "true" ] || SUMMARY=/dev/null

files=0
failed=0
shopt -s nullglob

while IFS= read -r pattern; do
	# without surrounding spaces and without the carriage return of a Windows line end
	pattern="$(printf '%s' "${pattern}" | sed -e 's/\r$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
	[ -n "${pattern}" ] || continue
	matched=0
	OLD_IFS="${IFS}"
	IFS=$'\n'

	# a pattern is expanded by the shell, and a name with spaces stays one name
	for file in ${pattern}; do
		IFS="${OLD_IFS}"
		matched=1
		files=$((files + 1))
		echo "::group::actuator-lint ${file}"
		status=0
		actuator-lint --fail-on "${FAIL_ON}" ${ARGUMENTS[@]+"${ARGUMENTS[@]}"} -- "${file}" || status=$?
		echo "::endgroup::"

		if [ "${status}" -eq 0 ]; then
			echo "${file}: no findings at or above '${FAIL_ON}'"
		elif [ "${status}" -eq 1 ]; then
			failed=$((failed + 1))
			echo "::error file=${file}::actuator-lint: findings at or above '${FAIL_ON}', see the report in the log"
		else
			failed=$((failed + 1))
			echo "::error file=${file}::actuator-lint could not check this file, see the log"
		fi

		if [ "${status}" -le 1 ]; then
			actuator-lint --format markdown --fail-on never ${ARGUMENTS[@]+"${ARGUMENTS[@]}"} -- "${file}" >> "${SUMMARY}"
			echo >> "${SUMMARY}"
		fi
	done

	IFS="${OLD_IFS}"

	if [ "${matched}" -eq 0 ]; then
		failed=$((failed + 1))
		echo "::error::actuator-lint: no file matches '${pattern}'"
	fi
done <<< "${INPUT_FILES:-}"

if [ "${files}" -eq 0 ] && [ "${failed}" -eq 0 ]; then
	echo "::error::actuator-lint: the input 'files' is empty"
	failed=1
fi

if [ -n "${GITHUB_OUTPUT:-}" ]; then
	echo "files=${files}" >> "${GITHUB_OUTPUT}"
	echo "failed=${failed}" >> "${GITHUB_OUTPUT}"
fi

echo "actuator-lint: ${files} file(s) checked, ${failed} failed"
[ "${failed}" -eq 0 ]
