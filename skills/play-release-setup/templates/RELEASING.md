# Releasing

A release is two steps: merge a PR that bumps `appVersionName` in `__BUILD_FILE__`, then tag the
merge commit.

```bash
git tag v1.2 && git push origin v1.2
```

With the `play-release` skill installed, asking your agent to release does both, and prompts
for the version and release notes.

The tag builds a signed bundle and uploads it to the Play **internal** testing track. Promoting
to production stays manual, in Play Console.

## How it works

```
version bump PR ──merge──▶ default branch ──tag v1.2──▶ .github/workflows/release.yml
    ├─ verify the tag matches appVersionName
    ├─ restore the upload keystore (and google-services.json) from secrets
    ├─ build and sign the bundle
    ├─ upload it with the release notes to the internal track
    └─ archive the bundle on the run
                                    ▼
             Play Console: internal ──(you, by hand)──▶ production
```

**The version lives in the build file.** `appVersionName` is the only version literal.
`versionCode` is derived from it - `1.2.3` becomes `versionCodeBase + 10203` - so the two cannot
drift apart. The build fails if the name is not `MAJOR.MINOR` or `MAJOR.MINOR.PATCH`, or if
minor or patch reaches 100. CI refuses to build a tag that disagrees with the build file.

Because the version belongs to the commit rather than to the CI run, a failed run consumes
nothing: re-run it and it is an exact retry. Any tag rebuilds to the same version locally.

**Codes only go up.** Play retires a `versionCode` permanently once a bundle with it has been
uploaded, even if it was never rolled out. `versionCodeBase` may be raised, never lowered.

**Signing** reads `keystore.properties` at the repo root locally, or the `KEYSTORE_FILE`,
`KEYSTORE_PASSWORD`, `KEY_ALIAS` and `KEY_PASSWORD` environment variables in CI. With neither,
the release build compiles unsigned.

**Release notes** are `distribution/whatsnew/whatsnew-en-US`, at most 500 characters; going over
fails the upload after the whole build. Add a locale with a sibling file such as
`whatsnew-es-ES`.

**Deobfuscation:** the R8 mapping travels inside the bundle, and Play extracts it. Nothing to
upload separately.

## One-time setup

### Signing key

Use the upload key the app is already published with. **Do not generate a new one** for an app
that is already on Play. Find its alias:

```bash
keytool -list -v -keystore /path/to/upload-keystore.jks
```

Compare the `SHA1` it prints with the **Upload key certificate** on Play Console's **App integrity** page (the console's
search box finds it if the menu has moved) to confirm it is the right key, and note the expiry
date.

### Play service account

See the play-release-setup skill's `references/play-console.md`, or Google's
[getting started guide](https://developers.google.com/android-publisher/getting_started). In
short: enable the Google Play Android Developer API on a Cloud project, create a service account
with a JSON key, and invite that account in Play Console under **Users and permissions** with
access to this app.

### Repository secrets

Run these yourself, from the root of the main checkout (worktrees lack gitignored files):

```bash
gh secret set KEYSTORE_BASE64 -R __REPO__ < <(base64 -i /path/to/upload-keystore.jks)
gh secret set KEY_ALIAS -R __REPO__            # prompts; input hidden
gh secret set KEYSTORE_PASSWORD -R __REPO__
gh secret set KEY_PASSWORD -R __REPO__
gh secret set PLAY_SERVICE_ACCOUNT_JSON -R __REPO__ < /path/to/service-account.json
__GOOGLE_SERVICES_SECRET_LINE__
```

Secrets are write-only. `gh secret list -R __REPO__` shows which exist but never their values.

## Building a signed release locally

Create `keystore.properties` at the repo root. It is gitignored.

```properties
storeFile=/absolute/path/to/upload-keystore.jks
storePassword=...
keyAlias=...
keyPassword=...
```

Then `./gradlew :__MODULE__:__BUNDLE_TASK__`. A local build of a tagged commit carries the same
version as CI's.
