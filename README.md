- [GitHub Docker Processor](#h-B0FEE104)
  - [Features](#h-B46BEB64)
  - [Prerequisites](#h-3479049B)
  - [Installation](#h-37BEA592)
  - [Usage](#h-3A9FCC1E)
  - [Cleanup](#h-CF21FF2B)
- [Check Docker Digest](#h-A97A2D1E)
  - [Optional Builds](#h-BE3EA4F8)
- [Docker Hub Cleanup](#h-314F236D)



<a id="h-B0FEE104"></a>

# GitHub Docker Processor

This Python script automates the process of cloning multiple GitHub repositories and their specified branches, building Docker images for them, and pushing these images to DockerHub.


<a id="h-B46BEB64"></a>

## Features

Reads a YAML file containing a list of GitHub repositories and their respective branches. Builds Docker images from each branch and tags them according to the GitHub repository and branch name. Pushes Docker images to DockerHub.


<a id="h-3479049B"></a>

## Prerequisites

-   Python 3.x
-   Git
-   Docker
-   pyyaml package for Python


<a id="h-37BEA592"></a>

## Installation

```sh
git clone https://github.com/julienchastang/github_docker_processor.git
cd github_docker_processor
pip install pyyaml
docker login
chmod +x github_docker_processor.py
```


<a id="h-3A9FCC1E"></a>

## Usage

Create a YAML file:

```yaml
repositories:
  - url: https://github.com/User/repo
    branches:
      - "5.4"
      - "5.5"
  - url: https://github.com/AnotherUser/another-repo
    branches:
      - master
      - develop
```

Run the script:

```sh
sh github_docker_processor.py path_to_your_yaml_file.yaml
```

This script will ultimately push to DockerHub images that look like this:

```sh
docker push user/repo:5.4
docker push user/repo:5.5
docker push anotheruser/another-repo:master
docker push anotheruser/another-repo:develop
```


<a id="h-CF21FF2B"></a>

## Cleanup

The script will remove the cloned repositories from the local machine after each Docker image has been built and pushed.


<a id="h-A97A2D1E"></a>

# Check Docker Digest

This Python script is designed to check for updates to a specified Docker image according to a configuration file. It can send notifications of upstream image changes via email or ifttt. Here is an example configuration looking for updates to a Tomcat container:

```yaml
digest_file_path: "/tmp/tomcat-image-digest.txt"
repository: "library/tomcat"
tag: "8.5-jdk11"
target_architecture: "amd64"
sender: "user@example.edu"
recipient: "user@example.edu"
subject: "Upstream Tomcat Digest Updated"
ifttt_key: "https://maker.ifttt.com/trigger/<your_trigger_applet>/with/key/your_ifttt_key_here"
```

You can put this Python script in cron, e.g.,

```sh
0 */12 * * * /home/user/github-docker-automation/check_docker_digest.py \
  config.yml >> /tmp/tomcat-cron.out 2>&1
```


<a id="h-BE3EA4F8"></a>

## Optional Builds

`check_docker_digest.py` can build and push updated images to DockerHub in response to upstream changes. To enable this feature, add an optional `github_docker_repo` key in the configuration, which should link to the repository settings used by `github_docker_processor.py`. For example:

```yml
github_docker_repos: "repos.yml"
```


<a id="h-314F236D"></a>

# Docker Hub Cleanup

`dockerhub_cleanup.py` finds old or pattern-matched tags and repositories in any explicitly supplied Docker Hub namespace. It always runs as a non-destructive dry run unless `--execute` is given. Patterns use shell-style matching (`*`, `?`, and character ranges).

Preview tags older than 90 days in matching repositories:

```sh
python3 dockerhub_cleanup.py tags \
  --namespace exampleorg \
  --repository-pattern 'test-*' --older-than-days 90
```

Patterns can be repeated. This example previews tags whose names start with `snapshot-` or `dev-`:

```sh
python3 dockerhub_cleanup.py tags \
  --namespace exampleorg \
  --tag-pattern 'snapshot-*' --tag-pattern 'dev-*'
```

Preview entire repositories, which is a separate operation from tag cleanup:

```sh
python3 dockerhub_cleanup.py repositories \
  --namespace exampleorg \
  --repository-pattern 'test-*' --older-than-days 365
```

Review the dry-run output before deleting. For deletion, create a Docker Hub personal access token with **Repo Read, Write, Delete** permission and provide credentials through environment variables rather than files or command-line arguments:

```sh
export DOCKERHUB_USERNAME='your-dockerhub-user'
export DOCKERHUB_TOKEN='your-personal-access-token'

python3 dockerhub_cleanup.py tags \
  --namespace exampleorg \
  --repository-pattern '*' --tag-pattern 'snapshot-*' \
  --older-than-days 90 --execute
```

Credentials are optional for dry runs, but recommended for large namespaces because Docker Hub limits anonymous pagination. A read-only PAT is sufficient for a dry run and does not enable deletion without `--execute`:

```sh
export DOCKERHUB_USERNAME='your-dockerhub-user'
read -rsp 'Docker Hub PAT: ' DOCKERHUB_TOKEN
echo
export DOCKERHUB_TOKEN

python3 dockerhub_cleanup.py repositories --namespace exampleorg

unset DOCKERHUB_USERNAME DOCKERHUB_TOKEN
```

Both credential variables must be set together. Supplying credentials never changes the dry-run default.

Repository deletion requires both `--execute` and an exact namespace confirmation:

```sh
python3 dockerhub_cleanup.py repositories \
  --namespace exampleorg \
  --repository-pattern 'test-*' --older-than-days 365 \
  --execute --confirm-namespace exampleorg
```

For tag deletion, `--repository-pattern` must be supplied explicitly; use `'*'` only when intentionally applying the tag filters across the whole namespace. For either deletion command, at least one name or age filter is required. An item with a missing or invalid update timestamp is excluded when an age filter is active. Tag age means `tag_last_pushed` (falling back to `last_updated`), while repository age means the repository's `last_updated` value. Neither is a measure of when an image was last pulled, so an old item may still be actively used. The tool collects all candidates before deleting, follows Docker Hub pagination, retries rate limits and temporary server errors, reports individual deletion failures, and exits with a nonzero status if any deletion fails.

Run the focused tests with:

```sh
python3 -m unittest test_dockerhub_cleanup.py
```
