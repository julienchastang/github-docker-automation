import argparse
import datetime
import unittest
from unittest import mock

import dockerhub_cleanup


class FilteringTests(unittest.TestCase):
    def test_name_patterns_and_age_must_both_match(self):
        cutoff = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
        self.assertTrue(
            dockerhub_cleanup.matches(
                "test-old", ["test-*"], "2024-01-01T00:00:00Z", cutoff
            )
        )
        self.assertFalse(
            dockerhub_cleanup.matches(
                "other-old", ["test-*"], "2024-01-01T00:00:00Z", cutoff
            )
        )
        self.assertFalse(
            dockerhub_cleanup.matches(
                "test-new", ["test-*"], "2026-01-01T00:00:00Z", cutoff
            )
        )

    def test_unknown_date_does_not_match_age_filter(self):
        cutoff = datetime.datetime.now(datetime.timezone.utc)
        self.assertFalse(dockerhub_cleanup.matches("test-tag", ["*"], None, cutoff))


class ClientTests(unittest.TestCase):
    @mock.patch("urllib.request.urlopen")
    def test_requests_use_bearer_authentication(self, urlopen):
        urlopen.return_value.__enter__.return_value.read.return_value = b"{}"

        dockerhub_cleanup.DockerHubClient("test-access-token").request("GET", "/test")

        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.get_header("Authorization"), "Bearer test-access-token"
        )

    def test_pagination_follows_next_link(self):
        client = dockerhub_cleanup.DockerHubClient()
        client.request = mock.Mock(
            side_effect=[
                {"results": [{"name": "test-one"}], "next": "next-page"},
                {"results": [{"name": "test-two"}], "next": None},
            ]
        )

        self.assertEqual(
            [item["name"] for item in client.paginated("first-page")],
            ["test-one", "test-two"],
        )
        self.assertEqual(
            client.request.call_args_list,
            [mock.call("GET", "first-page"), mock.call("GET", "next-page")],
        )

    def test_authentication_uses_current_token_endpoint(self):
        with mock.patch.object(
            dockerhub_cleanup.DockerHubClient,
            "request",
            return_value={"access_token": "test-access-token"},
        ) as request:
            client = dockerhub_cleanup.DockerHubClient.login("test-user", "test-token")

        request.assert_called_once_with(
            "POST", "/auth/token", {"identifier": "test-user", "secret": "test-token"}
        )
        self.assertEqual(client.token, "test-access-token")

    def test_current_namespace_scoped_endpoints(self):
        client = dockerhub_cleanup.DockerHubClient()
        client.request = mock.Mock(return_value={})

        list(client.repositories("test-namespace"))
        list(client.tags("test-namespace", "test-repository"))
        client.delete_tag("test-namespace", "test-repository", "test-tag")
        client.delete_repository("test-namespace", "test-repository")

        self.assertEqual(
            client.request.call_args_list,
            [
                mock.call(
                    "GET", "/namespaces/test-namespace/repositories?page_size=100"
                ),
                mock.call(
                    "GET",
                    "/namespaces/test-namespace/repositories/"
                    "test-repository/tags?page_size=100",
                ),
                mock.call(
                    "DELETE",
                    "/namespaces/test-namespace/repositories/"
                    "test-repository/tags/test-tag",
                ),
                mock.call(
                    "DELETE", "/namespaces/test-namespace/repositories/test-repository"
                ),
            ],
        )


class SafetyTests(unittest.TestCase):
    def arguments(self, command, **changes):
        values = {
            "command": command,
            "execute": True,
            "namespace": "exampleorg",
            "repository_pattern": ["*"],
            "repository_filter_supplied": False,
            "older_than_days": None,
            "confirm_namespace": None,
        }
        if command == "tags":
            values["tag_pattern"] = ["*"]
        values.update(changes)
        if "repository_pattern" in changes:
            values["repository_filter_supplied"] = True
        return argparse.Namespace(**values)

    def test_tag_execution_requires_a_filter(self):
        with self.assertRaises(dockerhub_cleanup.DockerHubError):
            dockerhub_cleanup.validate_execution(self.arguments("tags"))

    def test_repository_execution_requires_filter_and_confirmation(self):
        args = self.arguments("repositories", repository_pattern=["test-*"])
        with self.assertRaises(dockerhub_cleanup.DockerHubError):
            dockerhub_cleanup.validate_execution(args)
        args.confirm_namespace = "differentorg"
        with self.assertRaises(dockerhub_cleanup.DockerHubError):
            dockerhub_cleanup.validate_execution(args)
        args.confirm_namespace = "exampleorg"
        dockerhub_cleanup.validate_execution(args)

    def test_namespace_is_required_for_each_command(self):
        parser = dockerhub_cleanup.build_parser()
        for command in ("repositories", "tags"):
            with self.subTest(command=command):
                with self.assertRaises(SystemExit):
                    parser.parse_args([command])

    def test_arbitrary_namespace_is_accepted_for_each_command(self):
        parser = dockerhub_cleanup.build_parser()
        for command in ("repositories", "tags"):
            with self.subTest(command=command):
                args = parser.parse_args([command, "--namespace", "exampleorg"])
                self.assertEqual(args.namespace, "exampleorg")

    @mock.patch.object(dockerhub_cleanup.DockerHubClient, "login")
    @mock.patch.dict(
        "os.environ",
        {
            "DOCKERHUB_USERNAME": "test-user",
            "DOCKERHUB_TOKEN": "test-token",
        },
        clear=True,
    )
    def test_tag_cleanup_only_calls_tag_deletion(self, login):
        client = login.return_value
        client.repositories.return_value = [
            {"name": "test-repository", "last_updated": "2024-01-01T00:00:00Z"}
        ]
        client.tags.return_value = [
            {"name": "test-tag", "last_updated": "2024-01-01T00:00:00Z"}
        ]
        args = self.arguments(
            "tags", repository_pattern=["test-*"], tag_pattern=["test-*"]
        )

        self.assertEqual(dockerhub_cleanup.run(args), 0)

        client.repositories.assert_called_once_with("exampleorg")
        client.tags.assert_called_once_with("exampleorg", "test-repository")
        client.delete_tag.assert_called_once_with(
            "exampleorg", "test-repository", "test-tag"
        )
        client.delete_repository.assert_not_called()

    @mock.patch.object(dockerhub_cleanup.DockerHubClient, "login")
    @mock.patch.dict(
        "os.environ",
        {
            "DOCKERHUB_USERNAME": "test-user",
            "DOCKERHUB_TOKEN": "test-token",
        },
        clear=True,
    )
    def test_all_tag_candidates_are_collected_before_deletion(self, login):
        client = login.return_value
        client.repositories.return_value = [
            {"name": "test-repository", "last_updated": "2024-01-01T00:00:00Z"}
        ]

        def tags():
            yield {"name": "test-one", "last_updated": "2024-01-01T00:00:00Z"}
            client.delete_tag.assert_not_called()
            yield {"name": "test-two", "last_updated": "2024-01-01T00:00:00Z"}
            client.delete_tag.assert_not_called()

        client.tags.return_value = tags()
        args = self.arguments(
            "tags", repository_pattern=["test-*"], tag_pattern=["test-*"]
        )

        self.assertEqual(dockerhub_cleanup.run(args), 0)
        self.assertEqual(client.delete_tag.call_count, 2)

    @mock.patch.object(dockerhub_cleanup.DockerHubClient, "login")
    @mock.patch.dict(
        "os.environ",
        {
            "DOCKERHUB_USERNAME": "test-user",
            "DOCKERHUB_TOKEN": "test-token",
        },
        clear=True,
    )
    def test_all_repository_candidates_are_collected_before_deletion(self, login):
        client = login.return_value

        def repositories():
            yield {"name": "test-one", "last_updated": "2024-01-01T00:00:00Z"}
            client.delete_repository.assert_not_called()
            yield {"name": "test-two", "last_updated": "2024-01-01T00:00:00Z"}
            client.delete_repository.assert_not_called()

        client.repositories.return_value = repositories()
        args = self.arguments(
            "repositories",
            repository_pattern=["test-*"],
            confirm_namespace="exampleorg",
        )

        self.assertEqual(dockerhub_cleanup.run(args), 0)
        client.repositories.assert_called_once_with("exampleorg")
        self.assertEqual(client.delete_repository.call_count, 2)
        client.delete_repository.assert_has_calls(
            [
                mock.call("exampleorg", "test-one"),
                mock.call("exampleorg", "test-two"),
            ]
        )

    @mock.patch.object(dockerhub_cleanup, "DockerHubClient")
    @mock.patch.dict("os.environ", {}, clear=True)
    def test_anonymous_dry_run_never_authenticates_or_deletes(self, client_class):
        client = client_class.return_value
        client.repositories.return_value = [
            {"name": "test-repository", "last_updated": "2024-01-01T00:00:00Z"}
        ]
        args = self.arguments("repositories", execute=False)

        self.assertEqual(dockerhub_cleanup.run(args), 0)
        client_class.login.assert_not_called()
        client.delete_repository.assert_not_called()
        client.delete_tag.assert_not_called()

    @mock.patch.object(dockerhub_cleanup.DockerHubClient, "login")
    @mock.patch.dict(
        "os.environ",
        {
            "DOCKERHUB_USERNAME": "test-user",
            "DOCKERHUB_TOKEN": "test-token",
        },
        clear=True,
    )
    def test_dry_run_authenticates_without_deleting(self, login):
        client = login.return_value
        client.repositories.return_value = [
            {"name": "test-repository", "last_updated": "2024-01-01T00:00:00Z"}
        ]
        args = self.arguments("repositories", execute=False)

        self.assertEqual(dockerhub_cleanup.run(args), 0)

        login.assert_called_once_with("test-user", "test-token")
        client.delete_repository.assert_not_called()
        client.delete_tag.assert_not_called()

    @mock.patch.dict(
        "os.environ",
        {
            "DOCKERHUB_USERNAME": "test-user",
        },
        clear=True,
    )
    def test_partial_dry_run_credentials_are_rejected(self):
        args = self.arguments("repositories", execute=False)

        with self.assertRaises(dockerhub_cleanup.DockerHubError):
            dockerhub_cleanup.run(args)


if __name__ == "__main__":
    unittest.main()
