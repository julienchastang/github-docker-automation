#!/usr/bin/env python3

import argparse
import os
import subprocess
import yaml


def docker_cleanup():
    print("Running Docker cleanup...")
    cmd = ["docker", "system", "prune", "-af"]
    subprocess.check_call(cmd)


def clone_repository(repo_url):
    repo_name = repo_url.split('/')[-1].replace('.git', '').lower()
    namespace = repo_url.split('/')[-2].lower()
    target_path = os.path.join('/tmp', repo_name)
    cmd = ["git", "clone", repo_url, target_path]
    subprocess.check_call(cmd)
    return repo_name, namespace, target_path


def checkout_branch(target_path, branch):
    cmd = ["git", "-C", target_path, "checkout", branch]
    subprocess.check_call(cmd)


def build_docker_image(repo_name, branch, namespace, target_path):
    image_name = f"{namespace}/{repo_name}:{branch}"
    cmd = ["docker", "build", "-t", image_name, target_path]
    subprocess.check_call(cmd)
    return image_name


def push_to_dockerhub(image_name):
    cmd = ["docker", "push", image_name]
    subprocess.check_call(cmd)


def main(args):
    # Make space for build(s)
    docker_cleanup()

    with open(args.yaml_file, 'r') as stream:
        data = yaml.safe_load(stream)

    for repo in data['repositories']:
        repo_name = None
        try:
            repo_url = repo['url']
            print(f"Cloning {repo_url}...")
            repo_name, namespace, target_path = clone_repository(repo_url)
            for branch in repo['branches']:
                print(f"Processing {repo_url} branch {branch}...")
                checkout_branch(target_path, branch)  # Use target_path
                image_name = build_docker_image(repo_name, branch, namespace,
                                                target_path)
                push_to_dockerhub(image_name)
        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            if target_path:
                subprocess.check_call(["rm", "-rf", target_path])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process GitHub repos from a'
                                     ' YAML file.')
    parser.add_argument('yaml_file', type=str, help='Path to the YAML file'
                        ' containing repository information.')
    args = parser.parse_args()

    main(args)
