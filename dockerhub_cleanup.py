#!/usr/bin/env python3

"""Find and remove old Docker Hub tags or repositories."""

import argparse
import datetime
import fnmatch
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional


API_URL = "https://hub.docker.com/v2"


class DockerHubError(Exception):
    """A Docker Hub request failed."""


class DockerHubClient:
    """Small client for the Docker Hub API endpoints used by this tool."""

    def __init__(self, token: Optional[str] = None) -> None:
        self.token = token

    @classmethod
    def login(cls, username: str, password: str) -> "DockerHubClient":
        client = cls()
        response = client.request(
            "POST", "/auth/token", {"identifier": username, "secret": password}
        )
        token = response.get("access_token")
        if not token:
            raise DockerHubError("Docker Hub authentication returned no token")
        return cls(token)

    def request(self, method: str, path: str, body: Optional[Dict[str, str]] = None):
        url = path if path.startswith("http") else API_URL + path
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        for attempt in range(3):
            try:
                request = urllib.request.Request(
                    url, data=data, headers=headers, method=method
                )
                with urllib.request.urlopen(request, timeout=30) as response:
                    content = response.read()
                    return json.loads(content) if content else {}
            except urllib.error.HTTPError as error:
                details = error.read().decode("utf-8", errors="replace")
                if error.code == 429 or error.code >= 500:
                    if attempt < 2:
                        retry_after = error.headers.get("Retry-After")
                        delay = (
                            int(retry_after)
                            if retry_after and retry_after.isdigit()
                            else attempt + 1
                        )
                        time.sleep(min(delay, 30))
                        continue
                raise DockerHubError(
                    f"Docker Hub returned HTTP {error.code} for {method} "
                    f"{url}: {details or error.reason}"
                ) from error
            except urllib.error.URLError as error:
                raise DockerHubError(
                    f"Could not reach Docker Hub for {method} {url}: {error.reason}"
                ) from error
        raise DockerHubError(f"Docker Hub request failed: {method} {url}")

    def paginated(self, path: str) -> Iterable[Dict[str, Any]]:
        next_url: Optional[str] = path
        while next_url:
            page = self.request("GET", next_url)
            yield from page.get("results", [])
            next_url = page.get("next")

    def repositories(self, namespace: str) -> Iterable[Dict[str, Any]]:
        namespace = urllib.parse.quote(namespace, safe="")
        return self.paginated(f"/namespaces/{namespace}/repositories?page_size=100")

    def tags(self, namespace: str, repository: str) -> Iterable[Dict[str, Any]]:
        namespace = urllib.parse.quote(namespace, safe="")
        repository = urllib.parse.quote(repository, safe="")
        return self.paginated(
            f"/namespaces/{namespace}/repositories/{repository}/tags?page_size=100"
        )

    def delete_tag(self, namespace: str, repository: str, tag: str) -> None:
        parts = [
            urllib.parse.quote(value, safe="") for value in (namespace, repository, tag)
        ]
        self.request(
            "DELETE", f"/namespaces/{parts[0]}/repositories/{parts[1]}/tags/{parts[2]}"
        )

    def delete_repository(self, namespace: str, repository: str) -> None:
        parts = [
            urllib.parse.quote(value, safe="") for value in (namespace, repository)
        ]
        self.request("DELETE", f"/namespaces/{parts[0]}/repositories/{parts[1]}")


def parse_date(value: Optional[str]) -> Optional[datetime.datetime]:
    """Parse a Docker Hub timestamp as an aware UTC datetime."""
    if not value:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def matches(
    name: str,
    patterns: List[str],
    updated: Optional[str],
    cutoff: Optional[datetime.datetime],
) -> bool:
    """Return whether a name and timestamp satisfy all supplied criteria."""
    if not any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns):
        return False
    if cutoff is None:
        return True
    timestamp = parse_date(updated)
    return timestamp is not None and timestamp < cutoff


def cutoff_for(days: Optional[int]) -> Optional[datetime.datetime]:
    if days is None:
        return None
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)


def selected_repositories(
    client: DockerHubClient,
    args: argparse.Namespace,
    cutoff: Optional[datetime.datetime],
) -> Iterable[Dict[str, Any]]:
    for repository in client.repositories(args.namespace):
        if matches(
            repository["name"],
            args.repository_pattern,
            repository.get("last_updated"),
            cutoff,
        ):
            yield repository


def credentials() -> tuple[str, str]:
    username = os.environ.get("DOCKERHUB_USERNAME")
    token = os.environ.get("DOCKERHUB_TOKEN")
    if not username or not token:
        raise DockerHubError("deletion requires DOCKERHUB_USERNAME and DOCKERHUB_TOKEN")
    return username, token


def validate_execution(args: argparse.Namespace) -> None:
    if not args.execute:
        return
    has_repository_filter = args.repository_pattern != ["*"]
    if args.command == "tags":
        if not args.repository_filter_supplied:
            raise DockerHubError(
                "tag deletion requires an explicit --repository-pattern "
                "(use '*' to acknowledge all repositories)"
            )
        if (
            not has_repository_filter
            and args.tag_pattern == ["*"]
            and args.older_than_days is None
        ):
            raise DockerHubError(
                "refusing to delete all tags without a name or age filter"
            )
    elif not has_repository_filter and args.older_than_days is None:
        raise DockerHubError(
            "refusing to delete all repositories without a name or age filter"
        )
    if args.command == "repositories" and args.confirm_namespace != args.namespace:
        raise DockerHubError(
            f"repository deletion requires --confirm-namespace {args.namespace}"
        )


def run(args: argparse.Namespace) -> int:
    validate_execution(args)
    client = DockerHubClient()
    has_credentials = os.environ.get("DOCKERHUB_USERNAME") or os.environ.get(
        "DOCKERHUB_TOKEN"
    )
    if has_credentials:
        client = DockerHubClient.login(*credentials())
    elif args.execute:
        credentials()

    failures = 0
    count = 0
    tag_cutoff = None
    if args.command == "tags":
        repository_cutoff = None
        tag_cutoff = cutoff_for(args.older_than_days)
    else:
        repository_cutoff = cutoff_for(args.older_than_days)

    repositories = list(selected_repositories(client, args, repository_cutoff))
    if args.command == "tags":
        candidates = []
        for repository in repositories:
            repository_name = repository["name"]
            for tag in client.tags(args.namespace, repository_name):
                updated = tag.get("tag_last_pushed") or tag.get("last_updated")
                if matches(tag["name"], args.tag_pattern, updated, tag_cutoff):
                    candidates.append((repository_name, tag, updated))

        for repository_name, tag, updated in candidates:
            target = f"{args.namespace}/{repository_name}:{tag['name']}"
            count += 1
            if not args.execute:
                print(f"would delete tag {target} (updated {updated or 'unknown'})")
                continue
            print(f"deleting tag {target} (updated {updated or 'unknown'})")
            try:
                client.delete_tag(args.namespace, repository_name, tag["name"])
                print(f"deleted tag {target}")
            except DockerHubError as error:
                failures += 1
                print(f"error: {error}", file=sys.stderr)
    else:
        for repository in repositories:
            repository_name = repository["name"]
            updated = repository.get("last_updated")
            target = f"{args.namespace}/{repository_name}"
            count += 1
            if not args.execute:
                print(
                    f"would delete repository {target} (updated {updated or 'unknown'})"
                )
                continue
            print(f"deleting repository {target} (updated {updated or 'unknown'})")
            try:
                client.delete_repository(args.namespace, repository_name)
                print(f"deleted repository {target}")
            except DockerHubError as error:
                failures += 1
                print(f"error: {error}", file=sys.stderr)

    action = "deleted" if args.execute else "found"
    print(
        f"{action} {count - failures} candidate(s)"
        + (f"; {failures} deletion(s) failed" if failures else "")
    )
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find and delete Docker Hub tags or repositories. "
        "Runs as a dry run unless --execute is supplied."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument(
            "--namespace",
            required=True,
            help="Docker Hub user or organization namespace",
        )
        subparser.add_argument(
            "--repository-pattern",
            action="append",
            default=None,
            help="repository shell pattern; repeat to match several",
        )
        subparser.add_argument(
            "--older-than-days",
            type=int,
            metavar="DAYS",
            help="only select items last updated more than DAYS ago",
        )
        subparser.add_argument(
            "--execute",
            action="store_true",
            help="perform deletions instead of displaying candidates",
        )

    tags = subparsers.add_parser("tags", help="clean up image tags")
    common(tags)
    tags.add_argument(
        "--tag-pattern",
        action="append",
        default=None,
        help="tag shell pattern; repeat to match several",
    )

    repositories = subparsers.add_parser(
        "repositories", help="clean up entire repositories"
    )
    common(repositories)
    repositories.add_argument(
        "--confirm-namespace",
        metavar="NAMESPACE",
        help="required with --execute; must equal --namespace",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.repository_filter_supplied = args.repository_pattern is not None
    args.repository_pattern = args.repository_pattern or ["*"]
    if args.command == "tags":
        args.tag_pattern = args.tag_pattern or ["*"]
    if args.older_than_days is not None and args.older_than_days < 0:
        parser.error("--older-than-days cannot be negative")
    try:
        return run(args)
    except DockerHubError as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    sys.exit(main())
