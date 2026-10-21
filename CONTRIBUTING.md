# Contributing

Read [`AGENTS.md`](AGENTS.md) first; it is the normative guide and this page only summarizes the
workflow.

## Pull requests

- PRs are squash-merged. Issue and PR templates are the organization defaults from
  `temporalio/.github`.
- Every path is owned by `@temporalio/compute` (see [`.github/CODEOWNERS`](.github/CODEOWNERS));
  PRs need one code-owner approval.
- Changes that need new or changed base SDK APIs land in the SDK repository first. A PR here can
  only depend on a released SDK version.

## Contributor License Agreement

All contributors must complete the Temporal Contributor License Agreement (CLA)
before changes can be merged. A link to the CLA will be posted in the pull request.
