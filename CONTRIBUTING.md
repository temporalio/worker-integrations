# Contributing

This contains concrete information about contributing. See [`README.md`](README.md) for a high-level
overview of the repository. Also see [`AGENTS.md`](AGENTS.md) for thorough details for coding
agents (and humans).

To make a contribution, just open a pull request with your package additions or modifications.
Once merged, it will be distributed in a new package version the next time the Temporal team
creates a release for that package.

## Set up

- For language-specific instructions on setup, adding new packages, and working on existing
  packages, see the README in the subdirectory for the relevant language.

## Pull requests

- The Temporal Compute team (`@temporalio/compute`) are the codeowners for this repository.
  PRs need one code-owner approval.
- CI runs only for the packages whose files changed. `ci-status` is the required check; it will
  fail if any individual CI check fails.
- If you are making a change in this repository that depends on base SDK changes, the changes in
  the SDK repositories must be accepted and released first. A PR here can only depend on a released
  SDK version.

## Contributor License Agreement

All contributors must complete the Temporal Contributor License Agreement (CLA)
before changes can be merged. A link to the CLA will be posted in the pull request.
