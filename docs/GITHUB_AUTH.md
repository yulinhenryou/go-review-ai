# Restore GitHub Write Access

Repository: `yulinhenryou/go-review-ai`. Do not make the repository more public,
disable branch protection, or share passwords/tokens in chat to resolve login.

There are two independent credentials: terminal Git HTTPS authentication and the
connected GitHub integration. Fixing one does not automatically fix the other.
The last terminal push failed authentication; the integration could read but its
write request returned 403. These failures do not delete local commits.

## Recommended: Terminal Browser Login

On this Mac, install GitHub CLI with Homebrew if `gh` is not installed:

```bash
brew install gh
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
gh auth status
```

Copy the one-time code shown by the CLI into the GitHub page it opens. Sign in
as `yulinhenryou`, review the requested access, and authorize GitHub CLI. Do not
send that code or any token to the assistant. The setup command configures Git
to use the CLI credential helper instead of an obsolete cached HTTPS token.
Sources: [CLI installation](https://github.com/cli/cli#installation),
[browser login](https://cli.github.com/manual/gh_auth_login),
[Git credential helper](https://cli.github.com/manual/gh_auth_setup-git).

Confirm account and repository permissions without printing secrets:

```bash
gh api user --jq .login
gh repo view yulinhenryou/go-review-ai --json viewerPermission
```

The account should be yours and permission should include write access, such as
WRITE, MAINTAIN or ADMIN. Read success alone does not prove push permission.
Tell the assistant when login is complete; it can fetch and safely synchronize
the saved main commit, the M1 branch and the local archive tag. Do not force-push
to resolve a rejected update. Do not use `gh auth token` or paste credentials
into a repository URL or shell command.

## Alternative: Fine-Grained Token

Use GitHub Settings > Developer settings > Personal access tokens > Fine-grained
tokens. Create a short-lived token with your account as Resource owner, select
only `go-review-ai`, and grant repository Contents read/write. Do not grant
unrelated organization, administration or secret permissions. Use the token only
through a trusted credential manager or Git's hidden password prompt.
GitHub account passwords do not authenticate HTTPS Git operations.
See [GitHub's token guide](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens).

Workflow-file changes require separate workflow permission. This M1 change does
not add workflows; leave that permission out unless it is needed later.

## Connected Integration

Open GitHub Settings > Applications > Installed GitHub Apps, locate the app used
by your connection and choose Configure. Under repository access, ensure
`go-review-ai` is selected; save the change. Review any pending permission
request from that app rather than approving unrelated access.
See [GitHub's app access instructions](https://docs.github.com/en/apps/using-github-apps/reviewing-and-modifying-installed-github-apps).

Repository selection cannot grant capabilities the app itself does not request.
If its requested Contents permission is read-only, selecting the repository or
reconnecting will not turn it into a writer. Use the terminal login above for
pushes. Do not repeatedly uninstall apps or relax repository protections.
