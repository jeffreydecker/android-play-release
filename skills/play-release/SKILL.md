---
name: play-release
description: Cut a Google Play release in a repo set up by play-release-setup - checks secrets, proposes the next version, drafts release notes for the user to approve, opens the version bump PR, then tags the merge and watches the upload to the internal track. Use when the user asks to ship, release, publish, or cut a version of an Android app, or invokes /play-release.
---

# Play release

Runs in two phases with a human gate between them. **Phase A** opens a version bump PR.
**Phase B**, after the user merges it, tags the commit the merge produced and watches the
upload. Pushing the tag is the only step that ships.

Check first whether a bump was merged and never tagged. If
`gh pr list --state merged --head release/v<version in the build file>` finds a PR and that tag
does not exist, go straight to phase B for that version. Do not open a second PR. A version with
no tag on its own proves nothing: right after setup, the build file holds the already-shipped
version, untagged.

Where this skill says to use AskUserQuestion, an agent without that tool asks in chat and waits
for the answer.

This skill expects the layout `play-release-setup` creates: `appVersionName` in the app module's
build file, `.github/workflows/release.yml`, and `distribution/whatsnew/`. If they are missing,
say so and suggest running the setup skill. Do not improvise a release process.

## 1. Discover and preflight

```bash
gh repo view --json nameWithOwner,defaultBranchRef -q '.nameWithOwner + " " + .defaultBranchRef.name'
# <gradle-path>
grep -oE '(:[A-Za-z0-9_.-]+)+:printVersionName' .github/workflows/release.yml | sed 's/:printVersionName$//'
# <build-file>
git grep -lE '^[[:space:]]*(val|def) appVersionName = ' -- '*build.gradle' '*build.gradle.kts'
# the secrets the workflow needs, and its <environment>, if any
grep -oE 'secrets\.[A-Z_]+' .github/workflows/release.yml | sort -u
grep -E '^[[:space:]]+environment:' .github/workflows/release.yml
gh secret list            # with an environment: gh secret list --env <environment>
```

The Gradle path can be nested, such as `:apps:android`, and the module directory need not match
it, so use the two values found above rather than deriving one from the other. The build file
search must find exactly one file.

All of these must hold. If any does not, stop and report which:

- the current branch is the default branch
- after `git fetch origin`, `git status -sb` shows it is not behind its remote
- no tracked file has uncommitted changes (untracked files are fine; you stage by name below)
- every secret the workflow references is in the secret list (the environment's, if the
  workflow names one)

For a missing secret, point the user at RELEASING.md. Never offer to set secrets by handling the
values yourself.

## 2. Pick the version

```bash
git tag --list 'v*' | sort -V | tail -5
sed -nE 's/^.*appVersionName = "(.*)"$/\1/p' <build-file>
```

To find the commits since the last release, use the last `v*` tag. With no tags, use the commit
that last changed the version line: `git log -1 --format=%h -G 'appVersionName = ' -- <build-file>`.
Use `-G`, which matches changed lines. `-S` only finds commits that change how many times the
string appears, and a version bump doesn't. Before the first tagged release that commit may be
the setup commit itself. In that case, find the version change before it with
`git log --format='%h %s' -G 'versionName' -- <build-file>`.

Show the current version and those commits, then use AskUserQuestion to offer the next patch and
the next minor. The user can type something else. The format is `MAJOR.MINOR` or
`MAJOR.MINOR.PATCH`, and minor and patch must stay under 100. Do not touch `versionCode`; it is
derived.

Check the tag is free: `git tag --list vX.Y` and `git ls-remote --tags origin refs/tags/vX.Y`.

## 3. Release notes

Draft notes for the people using the app, from what the commits changed. Do not copy commit
subjects. Leave out refactors, CI, and docs. Show the draft with AskUserQuestion so the user can
accept it or replace it.

`distribution/whatsnew/whatsnew-<locale>` is plain text, at most **500 characters** per file.
Count characters, not bytes, with `LC_ALL=en_US.UTF-8 wc -m`. `wc -c` overcounts anything
outside ASCII. Play rejects longer notes, and only at the very end of the run. If the directory
has other locales, ask whether to update them too, or remove the stale ones.

## 4. Phase A: the bump PR

Change only the `appVersionName` line. Then run `./gradlew -q <gradle-path>:printVersionName |
tail -n 1`. It proves the new name passes the build's version checks and prints the name the
workflow will compare against. Then:

```bash
git checkout -b release/vX.Y
git add <build-file> distribution/whatsnew/
git commit -m "Release vX.Y"
git push -u origin release/vX.Y
gh pr create --title "Release vX.Y" --body "<user-facing changes, the version, the derived versionCode>"
```

Give the user the PR link and stop. **Do not merge it** unless they explicitly ask.

## 5. Phase B: tag and ship

After the merge:

```bash
git checkout <default-branch> && git pull
./gradlew -q <gradle-path>:printVersionName | tail -n 1        # must equal X.Y
```

Find the commit the bump PR produced. With a merge commit it is the merge; with squash or rebase
merging it is the squashed or last rebased commit. GitHub reports it either way:

```bash
gh pr view release/vX.Y --json state,mergeCommit -q '.state + " " + .mergeCommit.oid'
```

Show the user that commit, the version, and the release notes. Ask for an explicit yes. Pushing the tag starts an upload that permanently uses up that versionCode. Ask again even
if they said "just release it" earlier.

```bash
git tag vX.Y <that-commit>
git push origin vX.Y
gh run list --workflow release.yml --event push --branch vX.Y --limit 1 --json databaseId,headSha,status
gh run watch <run-id> --exit-status
```

The run can take a few seconds to appear, so repeat `gh run list` until it does. For a tag push,
`--branch` matches the tag name. Check that `headSha` is the commit you tagged.

If the workflow's environment requires a reviewer, the run waits until someone approves it in
GitHub. Say so rather than reporting it as stuck. A release takes about 5 to 15 minutes. Watch
in the background if you can, rather than holding the conversation.

On success, say it is on the **internal** track. Say that testers must be on the track's tester
list and accept its opt-in link to see it, and that promoting to production is a manual step in
Play Console.

## When it fails

Read `gh run view <run-id> --log-failed` first. Then match the actual error against
`references/troubleshooting.md` in the play-release-setup skill. The cases that matter most:

- **Anything before `Upload to Play`, or a permissions error during it.** Fix the cause, then
  offer `gh run rerun <run-id>`. The version comes from the commit, so a re-run is an exact
  retry. But a re-run uploads to Play and uses up the versionCode just as the tag push did, so
  it needs its own explicit yes.
- **An error at `Committing the Edit` about a declaration** (foreground services and similar).
  This needs the manual upload path in troubleshooting.md. After a manual upload the versionCode
  is used up: do not re-run. The next release is a new version.
- **The wrong commit was tagged.** Deleting the tag does not stop the run it started. Cancel the
  run first, with `gh run cancel <run-id>`, and wait until `gh run view <run-id>` shows it
  cancelled. Then check whether `Upload to Play` ran at all. If it did not, show the user the
  tag and ask for a yes before deleting it:
  `git push origin :refs/tags/vX.Y && git tag -d vX.Y`. Then start phase B again. If the upload
  ran, treat it as uploaded (next case).
- **Anything uploaded to Play.** It cannot be taken back. Fix forward with a higher version.
