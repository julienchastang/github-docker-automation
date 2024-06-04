#!/usr/bin/env python3

"""
This script checks for hash updates and triggers Docker image build and push.
Can be scheduled in cron, e.g.,
*/10 * * * * /home/user/github-docker-automation/check-hash.py
tds-snap5-config.yml >> /tmp/tds-snap5.out 2>&1
"""

import argparse
import datetime
import os
import requests
import subprocess
import yaml
from typing import Optional


def fetch_hash(url: str) -> str:
    """Fetches the hash from the given URL."""
    response = requests.get(url)
    response.raise_for_status()
    return response.text.strip()


def read_hash_from_file(file_path: str) -> Optional[str]:
    """Reads the hash from the specified file."""
    if os.path.exists(file_path):
        with open(file_path, 'r') as file:
            return file.read().strip()
    return None


def write_hash_to_file(file_path: str, new_hash: str) -> None:
    """Writes the new hash to the specified file."""
    with open(file_path, 'w') as file:
        file.write(new_hash)


def main(yaml_file: str) -> None:
    """Main function that checks for hash updates and triggers Docker build."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    yaml_file_path = os.path.join(current_dir, yaml_file)

    with open(yaml_file_path, "r") as f:
        config = yaml.safe_load(f)

    hash_url = config['hash_url']
    hash_file_path = config['hash_file_path']
    github_docker_repos = config.get('github_docker_repos')

    current_hash = read_hash_from_file(hash_file_path)
    new_hash = fetch_hash(hash_url)

    if new_hash and new_hash != current_hash:
        now = datetime.datetime.now()
        print(f"New hash found: {new_hash} at {now}")
        write_hash_to_file(hash_file_path, new_hash)

        print("Building and pushing Docker image.")
        processor_script_path = os.path.join(current_dir,
                                             'github_docker_processor.py')
        github_docker_repos_path = os.path.join(current_dir,
                                                github_docker_repos)
        subprocess.run(['python3', processor_script_path,
                        github_docker_repos_path], check=True)
    else:
        print("No new hash. No update needed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check for hash updates and "
                                     "trigger Docker image build and push.")
    parser.add_argument("yaml_file", help="Path to the YAML configuration "
                        "file")
    args = parser.parse_args()
    main(args.yaml_file)
