"""TypeScript packages: naming, conventions checks, scaffolding and release versions.

Checks (see AGENTS.md, "TypeScript conventions"):
  * published-name is an npm name under the @temporalio scope, the folder is the name without its
    scope, and root-api equals it
  * required files exist
  * every [smoke] imports entry is a subpath export of the package
  * the Makefile is exactly the one-line stub that includes typescript/_shared/typescript.mk
  * package.json agrees with integration.toml (name, engines.node floor) and with repository policy
    (version placeholder, license, repository, LICENSE in files, packageManager, exports, no local
    dependencies, caret ranges on @temporalio packages)
  * pnpm-workspace.yaml's supply-chain cooldown, if set, exempts @temporalio packages

Release versions are `X.Y.Z`, or a SemVer pre-release of it with phase alpha, beta or rc, e.g.
`X.Y.Z-rc.1`.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

import yaml

from lib.common import Package
from lib.integration_toml import IntegrationMeta
from lib.languages._base import CheckContext, Language
from lib.release_version import ReleaseVersion, parse_semver_release

SCOPE = "@temporalio/"
# The name below the scope: lowercase letters and digits in `-`-separated words, starting with a
# letter. That's stricter than npm requires, and keeps folders out of what discovery ignores (names
# starting with `_` or `.`).
UNSCOPED_NAME_RE = re.compile(r"[a-z][a-z0-9]*(-[a-z0-9]+)*")
DEVELOPMENT_VERSION = "0.0.0"
REGISTRY_URL = "https://registry.npmjs.org"
REPOSITORY_URL = "git+https://github.com/temporalio/worker-integrations.git"
REQUIRED_FILES = ("package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml", "tsconfig.json", "Makefile", "README.md")
# Dependency tables in package.json, and the specs that point at local code instead of a published version
DEPENDENCY_TABLES = ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
LOCAL_SPEC_PREFIXES = ("workspace:", "file:", "link:", "portal:")
# Tables whose @temporalio/* specs users resolve against. Those specs must be caret ranges on the
# minimum supported version (e.g. ^1.24.0, meaning >=1.24.0 <2.0.0): the minimum is what CI's
# lowest-deps mode tests, and the cap keeps out the next major SDK version, which may break us.
# Exact pins aren't allowed: a user who upgrades the SDK but not this package would then install
# two copies of the SDK (including its native core), which is what happened with packages the SDK
# repositories published. Supporting two SDK majors at once (^1.24.0 || ^2.0.0) would need this
# rule loosened.
SDK_RANGE_TABLES = ("dependencies", "peerDependencies", "optionalDependencies")
CARET_RANGE_RE = re.compile(r"\^\d+\.\d+\.\d+")
SDK_PACKAGES_PATTERN = f"{SCOPE}*"


def folder_for(published_name: str) -> str:
    """The folder for a valid published name: the name without its scope."""
    return published_name.removeprefix(SCOPE)


class TypeScript(Language):
    name = "typescript"
    name_help = f"npm package name, e.g. {SCOPE}aws-lambda-worker"
    next_steps = """\
  1. Check that https://www.npmjs.com/package/{published_name} doesn't exist, unless this package
     is meant to continue that existing package.
  2. Set the real minimum supported SDK version, as a caret range, in package.json and in
     README.md's Compatibility section, and add the package's other dependencies, e.g.:
       cd typescript/{folder}
       pnpm pkg set 'dependencies["@temporalio/worker"]=^<version>'   # an older minimum (pnpm add can't)
       pnpm add <package>   # the newest version, as a caret range
       pnpm install         # commit the pnpm-lock.yaml it creates
  3. make lint && make test
  4. Before the package's first release, set it up on npm. If the package already exists on npm
     (see 1), ask someone who can publish @temporalio packages to run only the `npm trust` command
     in b, then release within 2 days of `npm trust` (see d). A new package needs more steps. npm
     can only set up trusted publishing for a package that exists, so a new package's first
     version must be published by hand, from the release dry run's tested tarball:
     a. Run the release dry run (see README.md's release steps) for a pre-release of the
        package's first version, e.g. typescript/{folder}/v0.1.0-rc.1 for a public-preview package.
     b. Within 7 days of the dry run (GitHub keeps its tarball that long), and once the next
        version is ready to follow within 2 days (see d), ask someone who can publish @temporalio
        packages to download the tarball, publish it, and set up the trusted publisher, with npm
        11.15.0 or newer:
          gh run download <dry run's run ID> -R temporalio/worker-integrations -n dist-{folder}
          npm publish <the tarball>.tgz --access public --tag next --ignore-scripts
          npm trust github {published_name} --repo temporalio/worker-integrations --file release-typescript.yml --env npm --allow-publish
     c. Publish the GitHub release for that version on the dry run's tested commit, as usual. The
        release workflow finds the version on npm, checks it's exactly the tested tarball, and
        skips the upload.
     d. Release the next version (another pre-release, or the final version) within 2 days of
        `npm trust`. npm drops a new trusted publisher that hasn't published within 2 days, and
        it would then have to be deleted and set up again. If the next version isn't ready, release
        another pre-release."""

    # -- scaffolding -----------------------------------------------------------------------------
    def package_folder(self, requested: str, published_name: str) -> str:
        return folder_for(published_name)

    def default_published_name(self, requested: str) -> str:
        return requested

    def validate_published_name(self, published_name: str) -> None:
        if not published_name.startswith(SCOPE) or not UNSCOPED_NAME_RE.fullmatch(published_name.removeprefix(SCOPE)):
            raise ValueError(
                f"npm package name must be {SCOPE}<name>, where <name> is lowercase letters and digits in "
                f"'-'-separated words, starting with a letter (e.g. {SCOPE}aws-lambda-worker), got {published_name!r}"
            )

    def substitutions(self, requested: str, published_name: str, description: str, maturity: str) -> dict[str, str]:
        return {
            "__NAME__": folder_for(published_name),
            "__PUBLISHED_NAME__": published_name,
            "__DESCRIPTION__": description,
            "__MATURITY__": maturity,
        }

    # -- conventions -----------------------------------------------------------------------------
    def check_package(self, ctx: CheckContext, package: Package, meta: IntegrationMeta | None) -> None:
        d, rel = package.path, package.rel
        for required in REQUIRED_FILES:
            if not (d / required).is_file():
                ctx.fail(f"{rel}: missing {required}")

        if meta is None:
            return  # integration.toml problems are already reported

        name = meta.published_name
        try:
            self.validate_published_name(name)
        except ValueError as exc:
            ctx.fail(f"{rel}/integration.toml: {exc}")
            return
        if package.name != folder_for(name):
            ctx.fail(f"{rel}: the folder for published-name {name!r} must be typescript/{folder_for(name)}")
            return
        if meta.root_api != name:
            ctx.fail(f"{rel}/integration.toml: root-api must equal published-name {name!r} (got {meta.root_api!r})")

        for import_path in meta.smoke_imports:
            if not import_path.startswith(f"{name}/"):
                ctx.fail(f"{rel}/integration.toml: [smoke] imports entry {import_path!r} must be a subpath of {name!r}")

        makefile = d / "Makefile"
        expected_makefile = "include ../_shared/typescript.mk\n"
        if makefile.is_file() and makefile.read_text() != expected_makefile:
            ctx.fail(f"{rel}/Makefile: must be exactly:\n{expected_makefile.rstrip()}")

        if not (d / "package.json").is_file():
            return
        try:
            manifest = json.loads((d / "package.json").read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            ctx.fail(f"{rel}/package.json: cannot parse: {exc}")
            return
        if not isinstance(manifest, dict):
            ctx.fail(f"{rel}/package.json: must be a JSON object")
            return
        _check_package_json(ctx, package, meta, manifest)
        _check_pnpm_workspace(ctx, package)

    # -- releases --------------------------------------------------------------------------------
    def release_version(self, text: str) -> ReleaseVersion:
        version = parse_semver_release(text)
        if version is None:
            raise ValueError(
                f"{text!r} isn't a supported TypeScript version: use X.Y.Z, or X.Y.Z followed by a pre-release "
                "-alpha.<N>, -beta.<N> or -rc.<N> (e.g. 1.0.0-rc.1)"
            )
        return version

    def published_versions(self, published_name: str) -> list[str]:
        # The packument's `time` maps every version ever published to its publish time, including
        # versions that were later unpublished (which npm never lets anyone reuse), alongside the
        # `created` and `modified` keys. If the whole package was unpublished, `time.unpublished`
        # lists its versions instead.
        packument = fetch_packument(published_name)
        if packument is None:
            return []
        time = packument.get("time", {})
        versions = set(packument.get("versions", {}))
        versions |= {key for key in time if key not in ("created", "modified", "unpublished")}
        versions |= set(time.get("unpublished", {}).get("versions", []))
        return sorted(versions)

    def may_already_be_published(self, version: ReleaseVersion, published: list[ReleaseVersion]) -> bool:
        # npm can only set up trusted publishing for a package that already exists, so a maintainer
        # publishes a new package's first version by hand, from the dry run's tested tarball (see
        # next_steps). The release workflow's publish job then checks that npm has exactly the
        # tested bytes, instead of uploading.
        return published == [version]


def fetch_packument(published_name: str) -> dict[str, Any] | None:
    """npm's metadata for a package (its "packument"), or None if npm has never had the package.

    Any error other than a 404 propagates, so that a registry outage fails a release instead of
    looking like an unpublished package.
    """
    url = f"{REGISTRY_URL}/{published_name.replace('/', '%2f')}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def _check_package_json(ctx: CheckContext, package: Package, meta: IntegrationMeta, manifest: dict[str, Any]) -> None:
    """Check the package's package.json for correctness and consistency with its integration.toml."""
    rel = f"{package.rel}/package.json"

    if manifest.get("name") != meta.published_name:
        ctx.fail(f"{rel}: name must be {meta.published_name!r} (got {manifest.get('name')!r})")

    if manifest.get("version") != DEVELOPMENT_VERSION:
        ctx.fail(
            f"{rel}: version must be the development placeholder {DEVELOPMENT_VERSION!r}; "
            f"release tags supply the published version (got {manifest.get('version')!r})"
        )

    if manifest.get("license") != "MIT":
        ctx.fail(f'{rel}: license must be "MIT"')
    files = manifest.get("files")
    if not isinstance(files, list) or "LICENSE" not in files:
        ctx.fail(f'{rel}: files must include "LICENSE"')

    # npm provenance requires repository.url to match the repository that publishes the package
    expected_repository = {"type": "git", "url": REPOSITORY_URL, "directory": f"typescript/{package.name}"}
    if manifest.get("repository") != expected_repository:
        ctx.fail(f"{rel}: repository must be {json.dumps(expected_repository)}")

    min_version = meta.runtime_versions[0]
    engines = manifest.get("engines")
    node_range = engines.get("node") if isinstance(engines, dict) else None
    if node_range != f">={min_version}":
        ctx.fail(
            f"{package.rel}: package.json's engines.node must be '>={min_version}', matching the first "
            f"[ci] runtime-versions entry (got {node_range!r})"
        )

    expected_package_manager = _template_package_manager(ctx)
    if expected_package_manager and manifest.get("packageManager") != expected_package_manager:
        ctx.fail(f"{rel}: packageManager must be typescript/_template's {expected_package_manager!r}")

    exports = manifest.get("exports")
    if not isinstance(exports, dict) or "." not in exports:
        ctx.fail(f'{rel}: exports must be an object with a "." entry')
    else:
        # The smoke test imports every subpath export (scripts/ci/typescript/smoke.py), so each must
        # be spelled out, because a pattern such as "./*" names no subpath it could import. Our
        # packages have few entry points, so listing them costs little. If a package ever needs a
        # pattern, allow it here and have the smoke test skip it (or import its expansions).
        for subpath in exports:
            if "*" in subpath:
                ctx.fail(f"{rel}: exports subpath {subpath!r} is a pattern; list each subpath explicitly")
        for import_path in meta.smoke_imports:
            subpath = "." + import_path.removeprefix(meta.published_name)
            if import_path.startswith(f"{meta.published_name}/") and subpath not in exports:
                ctx.fail(f"{rel}: exports must have a {subpath!r} entry for [smoke] imports entry {import_path!r}")

    # Packages are published independently of each other and of the SDK, so they depend on
    # published versions only
    for table in DEPENDENCY_TABLES:
        deps = manifest.get(table, {})
        if not isinstance(deps, dict):
            ctx.fail(f"{rel}: {table} must be an object")
            continue
        for dep, spec in deps.items():
            if isinstance(spec, str) and spec.startswith(LOCAL_SPEC_PREFIXES):
                ctx.fail(f"{rel}: {table} {dep} uses a local {spec.split(':')[0]}: spec; depend on published versions")
            elif (
                table in SDK_RANGE_TABLES
                and dep.startswith(SCOPE)
                and not (isinstance(spec, str) and CARET_RANGE_RE.fullmatch(spec))
            ):
                ctx.fail(
                    f"{rel}: {table} {dep} must be a caret range on its minimum supported version, "
                    f"e.g. ^1.24.0 (got {spec!r})"
                )


def _check_pnpm_workspace(ctx: CheckContext, package: Package) -> None:
    """Check the package's pnpm settings against repository policy."""
    path = package.path / "pnpm-workspace.yaml"
    if not path.is_file():
        return  # reported as a missing required file
    rel = f"{package.rel}/pnpm-workspace.yaml"
    try:
        settings = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        ctx.fail(f"{rel}: cannot parse: {exc}")
        return
    if not isinstance(settings, dict):
        ctx.fail(f"{rel}: must be a mapping of pnpm settings")
        return

    # The SDK should be exempted from the cooldown, i.e. new SDK versions can be used immediately
    excluded = settings.get("minimumReleaseAgeExclude") or []
    if settings.get("minimumReleaseAge") and SDK_PACKAGES_PATTERN not in excluded:
        ctx.fail(
            f"{rel}: minimumReleaseAge is set but {SCOPE} packages are not exempted "
            f"(add {SDK_PACKAGES_PATTERN!r} to minimumReleaseAgeExclude)"
        )


def _template_package_manager(ctx: CheckContext) -> str | None:
    """The packageManager that typescript/_template pins, which every package must match."""
    path = ctx.root / "typescript" / "_template" / "package.json.tmpl"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("packageManager")
