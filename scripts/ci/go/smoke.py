#!/usr/bin/env python3
"""Smoke-test a published version of one Go module, the way a user would get it.

Runs in release-go.yml after a release is published. Publishing the GitHub release creates the tag,
and the tag is the release: Go fetches modules straight from their repository, through the vanity
import page and the module proxy. Checks, in order:
  * go.temporal.io serves the module's vanity import page, with the go-import tag that points to
    the module's folder in this repository (see new_package.py's next steps)
  * the module proxy serves the version. The proxy fetches a new tag on its first request, which
    can fail for a while after the tag is created, so this waits for it.
  * the go command downloads the version through the proxy and verifies it against the checksum
    database
  * a new module that requires the version builds, importing the module's root package and
    integration.toml's [smoke] imports

The go command always uses the public module proxy and checksum database here, a fresh module
cache, and only the Go that's installed (GOTOOLCHAIN=local), whatever the environment sets.

Exits non-zero with the first problem.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lib.common import REPO_URL  # noqa: E402
from lib.integration_toml import IntegrationMeta  # noqa: E402
from lib.languages.go import folder_for  # noqa: E402

PROXY = "https://proxy.golang.org"
SUMDB = "sum.golang.org"
# How long to wait for the proxy to serve a new tag: up to 10 checks, 30 seconds apart
PROXY_CHECKS = 10
PROXY_CHECK_DELAY = 30


class SmokeFailure(Exception):
    """A problem with the published module. The message says what's wrong."""


class _GoImportTags(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "meta" and attributes.get("name") == "go-import":
            self.tags.append(" ".join((attributes.get("content") or "").split()))


def check_vanity_page(module_path: str) -> None:
    """Check that go.temporal.io routes `module_path` to its folder in this repository."""
    url = f"https://{module_path}?go-get=1"
    expected = f"{module_path} git {REPO_URL} go/{folder_for(module_path)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            parser = _GoImportTags()
            parser.feed(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise SmokeFailure(f"{url} returned HTTP {exc.code}; the module needs a vanity import page with go-import tag {expected!r}") from exc
    if expected not in parser.tags:
        raise SmokeFailure(f"{url} must have go-import tag {expected!r} (got {parser.tags})")


def go_env(root: Path, proxy: str, sumdb: str) -> dict[str, str]:
    """An environment for the go command that uses only `proxy` and `sumdb`, and a module cache in `root`."""
    return {
        **os.environ,
        "GOPROXY": proxy,
        "GOSUMDB": sumdb,
        "GOPRIVATE": "",
        "GONOPROXY": "",
        "GONOSUMDB": "",
        "GOWORK": "off",
        "GOTOOLCHAIN": "local",
        "GOMODCACHE": str(root / "modcache"),
        # The module cache is read-only by default, which would stop the temporary directory's cleanup
        "GOFLAGS": "-modcacherw",
    }


def _go(env: dict[str, str], cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["go", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=300)


def wait_for_proxy(module_path: str, version: str, proxy: str = PROXY) -> None:
    """Wait until `proxy` serves `module_path` at `version` (without its "v")."""
    url = f"{proxy}/{module_path}/@v/v{version}.info"
    for check in range(1, PROXY_CHECKS + 1):
        try:
            with urllib.request.urlopen(url, timeout=30):
                return
        except urllib.error.HTTPError as exc:
            # The proxy says "not found" with 404 or 410 until it can fetch the tag; anything else
            # is a real problem
            if exc.code not in (404, 410):
                raise SmokeFailure(f"{url} returned HTTP {exc.code}") from exc
        except urllib.error.URLError:
            pass  # e.g. a network blip
        if check < PROXY_CHECKS:
            print(f"{url} isn't available yet (check {check}/{PROXY_CHECKS}); retrying in {PROXY_CHECK_DELAY}s", flush=True)
            time.sleep(PROXY_CHECK_DELAY)
    raise SmokeFailure(f"{url} still wasn't available after {PROXY_CHECKS} checks")


def download_and_build(module_path: str, version: str, imports: list[str], proxy: str = PROXY, sumdb: str = SUMDB) -> None:
    """Download `module_path` at `version` (without its "v") through `proxy`, then build a module that imports it."""
    query = f"{module_path}@v{version}"
    with tempfile.TemporaryDirectory(prefix="go-smoke-") as directory:
        root = Path(directory)
        env = go_env(root, proxy, sumdb)
        result = _go(env, root, "mod", "download", "-json", query)
        if result.returncode != 0:
            raise SmokeFailure(f"`go mod download {query}` failed:\n{result.stdout}{result.stderr}")
        downloaded = json.loads(result.stdout)
        if downloaded.get("Version") != f"v{version}":
            raise SmokeFailure(f"{proxy} served {downloaded.get('Version')!r} for {query}")

        consumer = root / "consumer"
        consumer.mkdir()
        blank_imports = "\n".join(f'\t_ "{path}"' for path in [module_path, *imports])
        (consumer / "main.go").write_text(f"""\
package main

import (
{blank_imports}
)

func main() {{}}
""")
        for args in (("mod", "init", "smoke.test/consumer"), ("get", query), ("mod", "tidy"), ("build", "./...")):
            result = _go(env, consumer, *args)
            if result.returncode != 0:
                raise SmokeFailure(f"`go {' '.join(args)}` failed in a module that imports {query}:\n{result.stdout}{result.stderr}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--package-dir", type=Path, required=True, help="e.g. go/aws/lambda")
    parser.add_argument("--version", required=True, help="the published version, without the tag's \"v\"")
    args = parser.parse_args(argv)

    meta = IntegrationMeta.from_file(args.package_dir / "integration.toml")
    try:
        check_vanity_page(meta.published_name)
        wait_for_proxy(meta.published_name, args.version)
        download_and_build(meta.published_name, args.version, list(meta.smoke_imports))
    except SmokeFailure as exc:
        print(f"FAIL: {exc}")
        return 1
    print(f"OK: {meta.published_name}@v{args.version} downloads and builds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
