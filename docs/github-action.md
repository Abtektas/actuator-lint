# GitHub Action

The repository is also a GitHub Action: a workflow step that installs a
release of px4-ca-lint on the runner, checks the parameter files you name and
adds their reports to the job summary. The step fails when a file has a
finding at or above `fail-on`.

```yaml
name: control allocation
on: [push, pull_request]

permissions:
  contents: read

jobs:
  px4-ca-lint:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v7
      - uses: Abtektas/px4-ca-lint@v0.4.1
        with:
          files: |
            config/vehicle.params
            airframes/*.params
```

Name a release (`@v0.4.1`) or a full commit SHA, not `main`, so that a later
change of the action cannot change your workflow. The `version` input defaults
to the release of the action itself.

## Inputs

| Input | Default | Meaning |
|---|---|---|
| `files` | required | Parameter files, one per line. A line can be a pattern such as `config/*.params` (`**` is not supported). A line that matches no file is an error. |
| `fail-on` | `error` | Lowest finding level that fails the step: `warning`, `error` or `never`. |
| `arguments` | empty | Further options for every file, for example `--ignore CA011` or `--max-thrust-gain 3`. |
| `summary` | `true` | Whether the Markdown reports are added to the job summary. |
| `version` | `0.4.1` | Release of px4-ca-lint to install. |

## Outputs

| Output | Meaning |
|---|---|
| `files` | Number of files checked. |
| `failed` | Number of files with findings at or above `fail-on`, or that could not be checked. |

## What it needs

- A GitHub-hosted runner for Linux x86_64 or arm64 (`ubuntu-24.04`,
  `ubuntu-24.04-arm`) or macOS arm64, with Python 3.11 or newer. These are
  the platforms of the prebuilt engines; Ubuntu 22.04 is too old for them.
- Network access to github.com. The action downloads the Python package and
  the engine of the release, checks the engine against the checksums of the
  release and, with the GitHub CLI of the runner, that it was built by the
  release workflow of this repository.

## What a result means

The engine of a release contains the control allocation code of one PX4
version, which every report names; a result is only valid for that version.
A step that passes means that the tool found nothing at or above `fail-on`.
It does not mean that the configuration is safe: the
[safety and liability](../README.md#safety-and-liability) notes of the README
apply to the action as they do to the tool, and every report ends with them.
