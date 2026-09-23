# android-play-release

Agent skills that set up and run tag-driven Google Play releases for Android apps on GitHub
Actions.

You push `v1.2`. CI checks that the tag matches the version in your build file, builds and signs
the bundle, and uploads it with release notes to the Play internal track. Promoting to
production stays with you.

Two skills:

- **`play-release-setup`** configures a repo once. It reads your project to find the module,
  flavors, package, and signing, shows you a plan, makes the changes, and checks them with a real
  signed build. It finishes with a checklist of the things only you can do.
- **`play-release`** handles each release. It proposes the next version, drafts release notes for
  you to approve, opens the version bump PR, and after you merge it, tags the merge and watches
  the upload.

These skills came out of a real app's first automated release. Every failure it hit is written
up in [troubleshooting.md](skills/play-release-setup/references/troubleshooting.md), so the setup
can warn about each one before you run into it.

## What it will never do

This pipeline handles your upload key and a Play service account key, so here are the limits:

- **It never touches credentials.** It does not ask for, type, or store passwords, keystores, or
  service account keys. You set every secret yourself with commands it gives you.
- **It never publishes on its own.** It does not push tags, merge PRs, or promote releases
  without an explicit yes each time. Setup does none of these at all.
- **It pins third-party actions to commits.** The upload action gets your service account key,
  so a moved tag can't swap in different code.
- **It uploads to the internal track only.** Production is a button you press in Play Console.

## Design

- **The version lives in the build file, not the CI run.** `appVersionName` is the only version
  literal. `versionCode` is derived from it (`1.2.3` → `10203`, plus an optional base for apps
  that already have high codes). A failed run doesn't use up a version, so re-running is an exact
  retry. Any tag rebuilds the same version locally. Codes based on the run number, the common
  alternative, silently reset to 1 if the workflow file is renamed.
- **A bump PR before every tag.** The release is reviewed as a diff. The workflow refuses to build
  a tag that disagrees with the build file, and it checks this before the build starts.
- **Signing that degrades gracefully.** Credentials come from `keystore.properties` locally or
  environment variables in CI. With neither, release builds still compile, unsigned.

## Install

The skills use the standard `SKILL.md` format. For Claude Code:

```bash
git clone https://github.com/jeffreydecker/android-play-release
cp -r android-play-release/skills/* ~/.claude/skills/
```

Install both skills. `play-release` refers to the troubleshooting guide that ships with
`play-release-setup`.

## Usage

In your Android repo, ask your agent to *set up automated Play releases*. It will ask for what it
can't find out itself: the highest `versionCode` you have ever uploaded to Play, whether the
current version is already on Play, and your store listing's default language.

After setup and the one-time secrets, ask it to *cut a release*.

## Requirements

- An Android app that already has at least one release on Play. The Play API can't create an app
  or publish to a never-published one.
- A GitHub repository with Actions enabled, and an authenticated [`gh`](https://cli.github.com)
  CLI.
- Gradle with the Kotlin or Groovy DSL. Tested with AGP 9.3 and Gradle 9.7. The signing and
  version logic is plain Gradle and should work much further back.

## Limitations

- One application module and one package, Android App Bundles only, GitHub-hosted runners.
- Secrets live in a GitHub Environment that only `v*` tags can use. Private repos on GitHub Free
  can't have environments, so they fall back to repository secrets.
- Uploads go to the internal track. Other tracks and staged rollouts mean editing the workflow.
- Release notes start in one language, your listing's default. Add more as sibling files.

## Keeping it current

- **Pinned actions.** Keep the SHAs fresh by enabling Dependabot for `github-actions` in each
  repo that uses the workflow. It understands SHA pins with version comments.
- **Play Console.** The UI moves. The navigation in
  [play-console.md](skills/play-release-setup/references/play-console.md) was last checked in
  August 2026. If a menu path is wrong, please open an issue or a PR. That file is where most
  fixes will be needed.

## License

MIT. See [LICENSE](LICENSE).
