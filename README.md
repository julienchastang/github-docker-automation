- [GitHub Docker Processor](#h-B0FEE104)
  - [Features](#h-B46BEB64)
  - [Prerequisites](#h-3479049B)
  - [Installation](#h-37BEA592)
  - [Usage](#h-3A9FCC1E)
  - [Cleanup](#h-CF21FF2B)
- [Check Docker Digest](#h-A97A2D1E)



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
ifttt_key: "your_ifttt_key_here"
```

You can put this Python script in cron, e.g.,

```sh
0 */12 * * * /home/user/github-docker-automation/check-docker-digest.py \
  config.yml >> /tmp/tomcat-cron.out 2>&1
```
