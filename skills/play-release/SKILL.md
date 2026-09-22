---
name: play-release
description: Cut a Google Play release in a repo set up by play-release-setup - checks secrets, proposes the next version, drafts release notes for the user to approve, opens the version bump PR, then tags the merge and watches the upload to the internal track. Use when the user asks to ship, release, publish, or cut a version of an Android app, or invokes /play-release.
---

# Play release

Runs in two phases with a human gate between them. **Phase A** opens a version bump PR.
**Phase B**, after the user merges it, tags the merge commit and watches the upload. Pushing the
tag is the only step that ships.

If a release PR for the version is already merged, go straight to phase B. Do not open a second
one.

This skill expects the layout `play-release-setup` creates: `appVersionName` in the app module's
build file, `.github/workflows/release.yml`, and `distribution/whatsnew/`. If they are missing,
say so and suggest running the setup skill. Do not improvise a release process.

## 1. Discover and preflight

```bash
gh repo view --json nameWithOwner,defaultBranchRef -q '.nameWithOwner + " " + .defaultBranchRef.name'
grep -oE ':[A-Za-z0-9_-]+:printVersionName' .github/workflows/release.yml   # the app module
grep -oE 'secrets\.[A-Z_]+' .github/workflows/release.yml | sort -u         # secrets it needs
gh secret list
```

Then stop and report if any of these fail:

- the current branch is not the default branch
- `git fetch origin` and `git status -sb` show it is not behind its remote
- no tracked file has uncommitted changes (untracked files are fine; you stage by name below)
- every secret the workflow references exists in `gh secret list`

For a missing secret, point the user at RELEASING.md. Never offer to set secrets by handling the
values yourself.

## 2. Pick the version

```bash
git tag --list 'v*' | sort -V | tail -5
sed -nE 's/^.*appVersionName = "(.*)"$/\1/p' <module>/build.gradle*
```

To find the commits since the last release, use the last `v*` tag. With no tags, use the commit
that last changed the version line: `git log -1 --format=%h -S appVersionName -- <module>/build.gradle*`
Before a first tagged release that may be the setup commit itself. In that case, find the
previous `versionName` change with `git log -S versionName`.

Show the current version and those commits, then use AskUserQuestion to offer the next patch and
the next minor. The user can type something else. The format is `MAJOR.MINOR` or
`MAJOR.MINOR.PATCH`, and minor and patch must stay under 100. Do not touch `versionCode`; it is
derived.

Check the tag is free: `git tag --list vX.Y` and `git ls-remote --tags origin refs/tags/vX.Y`.

## 3. Release notes

Draft notes for the people using the app, from what the commits changed. Do not copy commit
subjects. Leave out refactors, CI, and docs. Show the draft with AskUserQuestion so the user can
accept it or replace it.

`distribution/whatsnew/whatsnew-en-US` is plain text, at most **500 characters**. Check with
`wc -c`. Play rejects longer notes, and only at the very end of the run. If the directory has
other locales, ask whether to update them too, or remove the stale ones.

## 4. Phase A: the bump PR

Change only the `appVersionName` line, then:

```bash
git checkout -b release/vX.Y
git add <module>/build.gradle* distribution/whatsnew/
git commit -m "Release vX.Y"
git push -u origin release/vX.Y
gh pr create --title "Release vX.Y" --body "<user-facing changes, the version, the derived versionCode>"
```

Before committing, run `./gradlew -q :<module>:printVersionName | tail -n 1`. It proves the new
name passes the build's version checks and prints the name the workflow will compare against.

Give the user the PR link and stop. **Do not merge it** unless they explicitly ask.

## 5. Phase B: tag and ship

After the merge:

```bash
git checkout <default-branch> && git pull
./gradlew -q :<module>:printVersionName | tail -n 1        # must equal X.Y
```

Show the user the commit you will tag, the version, and the release notes. Ask for an explicit
yes. Pushing the tag starts an upload that permanently uses up that versionCode. Ask again even
if they said "just release it" earlier.

```bash
git tag vX.Y <merge-commit>
git push origin vX.Y
gh run watch <run-id> --exit-status
```

A release takes about 5 to 15 minutes. Watch in the background if you can, rather than holding
the conversation.

On success, say it is on the **internal** track. Say that testers must be on the track's tester
list and accept its opt-in link to see it, and that promoting to production is a manual step in
Play Console.

## When it fails

Read `gh run view <run-id> --log-failed` first. Then match the actual error against
`references/troubleshooting.md` in the play-release-setup skill. The cases that matter most:

- **Anything before `Upload to Play`, or a permissions error during it.** Fix the cause, then run
  `gh run rerun <run-id>`. The version comes from the commit, so a re-run is an exact retry.
- **An error at `Committing the Edit` about a declaration** (foreground services and similar).
  This needs the manual upload path in troubleshooting.md. After a manual upload the versionCode
  is used up: do not re-run. The next release is a new version.
- **The wrong commit was tagged and nothing has been uploaded yet.** Run
  `git push origin :refs/tags/vX.Y && git tag -d vX.Y`, then start phase B again.
- **Anything uploaded to Play.** It cannot be taken back. Fix forward with a higher version.
