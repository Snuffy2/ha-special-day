# Releasing ha-special-day

Release Please manages the release pull request, version tag, and GitHub
Release from conventional commits merged to `main`.

The release pull request updates all version sources together:

- `.release-please-manifest.json`
- `custom_components/ha_special_day/const.py`
- `custom_components/ha_special_day/manifest.json`

Review and merge the release pull request after its normal required checks
pass. The next `Release Please` workflow run creates the `v`-prefixed tag and
GitHub Release, then builds and uploads `ha_special_day.zip` for HACS. Release Please
does not create or maintain a changelog file in this repository.

If archive creation or upload fails after the GitHub Release exists, manually
run the `Release Please` workflow with that release's `vMAJOR.MINOR.PATCH` tag.
The recovery run checks out the existing tag, validates its version sources,
and rebuilds and replaces `ha_special_day.zip` without creating another release.

The workflows use these repository secrets, matching the Places setup:

- `RELEASE_PLEASE_TOKEN` for release pull requests, tags, and archive uploads.
- `PREK_AUTOUPDATE_TOKEN` for hook-update pull requests.
- `PREK_AUTOFIX_TOKEN` for applying reviewed formatting fixes.

The ordinary test, validation, label, and coverage workflows use the provided
`GITHUB_TOKEN`. Release and hook-autoupdate jobs retain the Places fork guards.
Enable repository auto-merge if dependency updates should merge automatically.
