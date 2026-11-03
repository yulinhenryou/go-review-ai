#!/bin/sh
set -eu

command -v docker >/dev/null || {
    echo "Docker is required for the container acceptance check" >&2
    exit 1
}
test -z "$(git status --porcelain)" || {
    echo "Refusing to test an image from an uncommitted worktree" >&2
    exit 1
}
release=$(git rev-parse HEAD)
tag=go-review-ai:m5-local
container=go-review-ai-m5-acceptance
output=${1:-/tmp/go-review-m5-container.json}

cleanup() {
    docker rm --force "$container" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM
cleanup

docker build --build-arg "VCS_REF=$release" --tag "$tag" .
docker run --detach --name "$container" \
    --publish 127.0.0.1:8080:8080 \
    --env 'GO_REVIEW_PUBLIC_HOSTS=["127.0.0.1:8080"]' \
    "$tag" >/dev/null

attempt=0
until curl --fail --silent http://127.0.0.1:8080/health >/dev/null; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 150 ]; then
        docker logs "$container"
        exit 1
    fi
    sleep 2
done

.venv/bin/python scripts/remote_acceptance.py http://127.0.0.1:8080 --output "$output"
