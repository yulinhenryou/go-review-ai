#!/bin/sh
set -eu

app_name=${1:?Usage: scripts/deploy_fly.sh FLY_APP_NAME}
test -z "$(git status --porcelain)" || {
    echo "Refusing to deploy an uncommitted worktree" >&2
    exit 1
}
release=$(git rev-parse HEAD)

fly deploy \
    --app "$app_name" \
    --config deploy/fly.toml \
    --build-arg "VCS_REF=$release" \
    --remote-only

curl --fail --show-error --silent "https://${app_name}.fly.dev/release"
printf '\n'
curl --fail --show-error --silent "https://${app_name}.fly.dev/health"
printf '\n'
