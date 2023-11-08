#!/usr/bin/env python3

import subprocess
import yaml
import argparse


def clone_repository(repo_url):
    repo_name = repo_url.split('/')[-1].replace('.git', '').lower()
    namespace = repo_url.split('/')[-2].lower()
    cmd = ["git", "clone", repo_url]
    subprocess.check_call(cmd)
    return repo_name, namespace


def checkout_branch(repo_name, branch):
    cmd = ["git", "-C", repo_name, "checkout", branch]
    subprocess.check_call(cmd)


def build_docker_image(image_name, dockerfile_path="Dockerfile"):
    cmd = ["docker", "build", "-t", image_name, "-f", dockerfile_path, "."]
    subprocess.check_call(cmd)


def push_to_dockerhub(image_name):
    cmd = ["docker", "push", image_name]
    subprocess.check_call(cmd)


def main(args):
    with open(args.yaml_file, 'r') as stream:
        data = yaml.safe_load(stream)

    for repo in data['repositories']:
        try:
            repo_url = repo['url']
            repo_name, namespace = clone_repository(repo_url)
            image_name = repo.get('image_name', repo_name)
            dockerfile_path = repo.get('dockerfile_path', 'Dockerfile')
            print(f"Cloning {repo_url}...")
            for branch in repo['branches']:
                print(f"Processing {repo_url} branch {branch}...")
                checkout_branch(repo_name, branch)
                full_image_name = f"{namespace}/{image_name}:{branch}"
                build_docker_image(full_image_name, dockerfile_path)
                push_to_dockerhub(full_image_name)
        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            if repo_name:
                subprocess.check_call(["rm", "-rf", repo_name])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process GitHub repos from a'
                                     ' YAML file.')
    parser.add_argument('yaml_file', type=str, help='Path to the YAML file'
                        ' containing repository information.')
    args = parser.parse_args()

    main(args)
