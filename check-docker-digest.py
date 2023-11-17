#!/usr/bin/env python3

# Can put this Python script in cron, e.g.,
#
# 0 */12 * * * /home/user/github-docker-automation/check-docker-digest.py
# config.yml >> /tmp/tomcat-cron.out 2>&1

import argparse
import datetime
import os
import requests
import subprocess
import yaml


def get_image_manifest(repository, tag):
    dockerhub_url = "https://registry-1.docker.io"
    auth_url = "https://auth.docker.io/token"
    repo_scope = f"repository:{repository}:pull"

    # Get the authentication token
    response = requests.get(auth_url,
                            params={'service': 'registry.docker.io',
                                    'scope': repo_scope})
    response.raise_for_status()
    token = response.json()['token']

    # Get the image manifest list
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.docker.distribution.manifest.list.v2+json'
    }
    response = requests.get(f'{dockerhub_url}/v2/{repository}/manifests/{tag}',
                            headers=headers)
    response.raise_for_status()

    return response.json()


def get_image_digest_for_architecture(manifest_list, architecture):
    for manifest in manifest_list['manifests']:
        if (manifest['platform']['architecture'] == architecture
                and manifest['platform']['os'] == 'linux'):
            return manifest['digest']
    return None


def read_digest_from_file(file_path):
    with open(file_path, 'r') as file:
        return file.read().strip()


def write_digest_to_file(file_path, digest):
    with open(file_path, 'w') as file:
        file.write(digest)


def send_email_via_sendmail(recipient, sender, subject, body):
    message = f"From: {sender}\nTo: {recipient}\nSubject: {subject}\n\n{body}"
    process = subprocess.Popen(["/usr/sbin/sendmail", recipient],
                               stdin=subprocess.PIPE)
    process.communicate(message.encode('utf-8'))


def main(yaml_file):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    yaml_file_path = os.path.join(current_dir, yaml_file)
    with open(yaml_file_path, "r") as f:
        config = yaml.safe_load(f)

    digest_file_path = config['digest_file_path']
    repository = config['repository']
    tag = config['tag']
    target_architecture = config['target_architecture']
    sender = config['sender']
    recipient = config['recipient']
    subject = config['subject']
    ifttt_key = config['ifttt_key']
    # optional key
    github_docker_repos = config.get('github_docker_repos')

    try:
        current_digest = read_digest_from_file(digest_file_path)
    except FileNotFoundError:
        print(f"Digest file not found at {digest_file_path}. Creating a new "
              "file...")
        current_digest = ""

    manifest_list = get_image_manifest(repository, tag)
    new_digest = get_image_digest_for_architecture(manifest_list,
                                                   target_architecture)

    if new_digest != current_digest:
        now = datetime.datetime.now()
        print(f"New digest found: {new_digest} at {now}")
        write_digest_to_file(digest_file_path, new_digest)

        requests.get(ifttt_key)

        body = f"New digest found: {new_digest} at {now}"
        send_email_via_sendmail(recipient, sender, subject, body)
        print(f"Updated digest in {digest_file_path}")

        if github_docker_repos:
            print("Building updated Docker images to push to DockerHub.")
            processor_script_path = os.path.join(current_dir,
                                                 'github_docker_processor.py')
            github_docker_repos_path = os.path.join(current_dir,
                                                    github_docker_repos)
            subprocess.run(['python3', processor_script_path,
                            github_docker_repos_path])
    else:
        print("Digests are the same. No update needed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check for Docker image "
                                     "updates.")
    parser.add_argument("yaml_file", help="Path to the YAML configuration "
                        "file")
    args = parser.parse_args()
    main(args.yaml_file)
