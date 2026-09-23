---
name: play-release-setup
description: Set up automated Google Play releases for an Android app on GitHub Actions - signed release builds, a version derived from one line in the build file, a workflow that uploads to the internal track when a v* tag is pushed, and the one-time Play Console and secrets hand-off. Use when the user wants to automate Play Store uploads, set up release CI for an Android app, or configure release signing in Gradle.
---

# Play release setup

Adds a tag-driven release pipeline to an Android repo:

- **Signing** in Gradle, from a gitignored `keystore.properties` locally or environment variables
  in CI.
- **One version literal.** `appVersionName` in the build file, with `versionCode` derived from it,
  so the two cannot drift.
- **A workflow** that runs on a `v*` tag: checks the tag against the build file, builds and signs
  the bundle, and uploads it with release notes to the Play **internal** track.
- **Docs and a hand-off** covering what only the user can do: secrets and Play Console.

Templates are in `templates/`. Read `references/play-console.md` and
`references/troubleshooting.md` before the hand-off; they hold what first releases actually
trip on.

## Ground rules

- **Never handle credentials.** Do not ask for, type, echo, or store passwords, keystores, or
  service account keys. Do not create Cloud service accounts or keys. Give the user the commands
  and let them run them.
- **Never publish anything.** Do not push tags, trigger uploads, merge PRs, or promote releases.
  This skill ends with a working, verified setup and a checklist.
- **Show the plan before editing.** Step 2 ends with the user confirming it. Replacing an existing
  signing or versioning scheme always needs an explicit yes.
- **Verify with a real build** (step 4). An untested workflow fails at the end of a 10-minute run
  instead of in the editor.

## 1. Discover

### The application module

Modules can sit at any depth, and the application plugin can be applied three ways. Start from
every build file and the places that can hide the plugin id:

```bash
git ls-files '*settings.gradle' '*settings.gradle.kts' '*build.gradle' '*build.gradle.kts'
grep -nE '"com\.android\.application"' gradle/*.versions.toml 2>/dev/null
grep -rlE 'com\.android\.application|ApplicationExtension' build-logic buildSrc 2>/dev/null
```

A module is an application module if its build file applies any of:

- **The plugin id**: `id("com.android.application")`, `id 'com.android.application'`, or
  `apply plugin: 'com.android.application'`.
- **A version catalog alias** for it. The accessor is the toml key with `-`, `_`, and `.` each
  turned into `.`: `android-application` becomes `alias(libs.plugins.android.application)`, and
  `androidApplication` (the Kotlin Multiplatform wizard's name) becomes
  `alias(libs.plugins.androidApplication)`.
- **A convention plugin** from `build-logic` or `buildSrc` that applies it. Find the id it is
  registered under (`gradlePlugin { plugins { register(...) { id = ... } } }`, or the file name of
  a precompiled script plugin) and search the build files for that id.

If more than one module qualifies (a phone app and a Wear OS app, a sample app), ask which one
ships to Play. Record two names for it, because the templates need both:

- **Gradle path**, such as `:app` or `:apps:android`, from `include(...)` in settings.
- **Directory**, relative to the repo root. It is the path with `:` turned into `/` unless
  settings remaps it (`project(":app").projectDir = file("android-app")`); check for that.

Confirm the path, and get the bundle task names, with
`./gradlew -q <path>:tasks --all | grep -E '^bundle[A-Za-z]*Release '`. A worktree has no
`local.properties`, so Gradle cannot find the SDK there: copy it in from the main checkout or
set `ANDROID_HOME`.

**Compose Multiplatform.** The shipping module is usually `composeApp` on AGP 8, or a separate
`androidApp` on AGP 9, which no longer allows the Kotlin Multiplatform plugin and
`com.android.application` in one module. Edit only the module that applies the application
plugin, never the shared one.

### The module's configuration

Read the module's build file in full, and any convention plugin it applies, and record:

| Value | Where it comes from |
| --- | --- |
| DSL | `build.gradle.kts` is Kotlin, `build.gradle` is Groovy |
| Package name | `applicationId` of the flavor that ships to Play, plus any `applicationIdSuffix`. This pipeline uploads one package. If several flavors ship under different package names, set up the one the user picks, and tell them the others would each need a workflow of their own, which this skill does not set up. |
| Release notes locale | the default language of the app's Play store listing. Ask; the repo can't show it. `en-US` works only if the listing has that language. |
| Variant | flavor + `Release`, e.g. `prodRelease`; plain `release` without flavors |
| Bundle task | `bundle` + capitalized variant, e.g. `bundleProdRelease` |
| Current version | existing `versionCode` / `versionName`, and how they are computed |
| Version overrides | a `versionCode` or `versionName` set on a product flavor, or through the variant API (`androidComponents { onVariants { ... } }` setting an output's `versionCode`). Either one wins over `defaultConfig` and silently discards the derived code. List each one; they are replaced along with the old scheme. |
| Existing signing | any `signingConfigs` block, and what the release build type uses today |
| JDK | the highest of `jvmToolchain`, `toolchainVersion` in `gradle/gradle-daemon-jvm.properties`, `compileOptions`, and `jvmTarget`; use 17 if none says higher |
| Google Services | whether `com.google.gms.google-services` is applied, directly, by catalog alias, or through a convention plugin |

### Files the build reads that git does not have

CI starts from a fresh checkout, which has only tracked files. Find every file the build reads
from disk, in the module's build file, the root build file, and any convention plugin, and check
each against git:

```bash
grep -nE 'properties|\.json|file\(' <each build file>
git check-ignore -v <each path found>
```

- **`google-services.json`**, if Google Services is applied. Find every copy with
  `find <dir> -name google-services.json -not -path '*/build/*'`. The plugin searches the most
  specific directories first (`src/<variant>/`, then the build type and flavor directories under
  `src/`) and the module directory itself last. Flavorless apps usually keep the file there, as
  `<dir>/google-services.json`. Use the copy the plugin reaches first for the release variant.
  If you can't tell, the plugin's "missing" error lists every path it tried, in order.
- **`local.properties`** usually holds only `sdk.dir`, which CI does not need because the runner
  sets `ANDROID_HOME`. If the build reads anything else from it, treat it like the next item.
- **Any other ignored file**, such as `secrets.properties`, `apikey.properties`, or the secrets
  Gradle plugin's properties file. Find out whether the release build fails without it or falls
  back to defaults (the secrets plugin reads `local.defaults.properties`). Each file the release
  build needs gets a restore step in the workflow and a secret of its own.

`keystore.properties` is the exception. The workflow supplies its values as environment
variables instead.

A tracked file needs nothing. If `google-services.json` is committed, leave it alone: it is not
a secret, and that repo made its own choice.

### The repository

```bash
gh repo view --json nameWithOwner,defaultBranchRef,visibility
gh api repos/{owner}/{repo}/actions/permissions
gh secret list
ls .github/workflows 2>/dev/null
git ls-files -s gradlew gradle/wrapper/gradle-wrapper.jar gradle/wrapper/gradle-wrapper.properties
```

Actions must be enabled. The permissions call needs admin access to the repo. If it returns 403
or 404, say you could not check, and ask the user to confirm that Actions is enabled. If
`allowed_actions` is not `all`, the pinned actions in the template must be allowed explicitly;
tell the user which. On a private repo, CI minutes come from the account's quota; a release run
takes roughly 5-15 minutes.

**The Gradle wrapper.** All three files must be tracked, and `gradlew` must be mode `100755`.
If it shows `100644`, often because it was committed from Windows, CI fails with
`Permission denied`. The fix is `git update-index --chmod=+x gradlew`, part of the setup commit.

**A release environment.** The template keeps the secrets in a GitHub Environment (named `play`
unless the user prefers another name) that only `v*` tags can deploy to. Repository secrets can
be read by a workflow pushed on any branch. Environments exist on public repos on every plan, but
on private repos only on paid plans (Pro, Team, Enterprise). If the repo can't have one, the
workflow falls back to repository secrets. Say so in the plan.

### Existing release automation

```bash
ls fastlane/Fastfile .github/workflows/release.yml 2>/dev/null
grep -rlE 'upload-google-play|supply|com\.github\.triplet\.play|androidpublisher' .github fastlane <build files> 2>/dev/null
```

Fastlane `supply`, Gradle Play Publisher (`com.github.triplet.play`), or a workflow that already
uploads to Play means this setup would replace something. Show the user what you found and ask
whether to replace it. Never leave two pipelines that both upload on a tag. Release notes kept
in `fastlane/metadata/android/<locale>/changelogs/` or `src/main/play/release-notes/` move to
`distribution/whatsnew/`. If `.github/workflows/release.yml` exists and does something else, ask
before overwriting it; the `play-release` skill expects the new workflow at that path.

### The version questions only the user can answer

Play remembers every `versionCode` ever uploaded, and the repo does not. Ask the user two things:

- the **highest versionCode uploaded to Play**. Play Console's App bundle explorer lists them.
  Do not assume it equals the build file's value: codes may have come from another branch, a
  manual upload, or an old scheme.
- whether the build file's **current versionName has been uploaded** already, or is the next
  release still in progress. The same page lists version names.

If the app has never been uploaded to Play, the first release must be done by hand in Play
Console. Say so now; the API cannot create an app or publish to a never-published app.

## 2. Plan the version scheme and confirm

`appVersionName` must be `MAJOR.MINOR` or `MAJOR.MINOR.PATCH` with minor and patch under 100.
Keep the current name if it fits. Otherwise propose the nearest valid one and ask.

The derived code is `versionCodeBase + major * 10000 + minor * 100 + patch`. What matters is the
lowest code the next release can get:

- if the current name has been uploaded, the next release is at least its next patch, so take
  the derived code of that patch
- if it has not, the next release may be the current name itself, so take its derived code

Set `versionCodeBase = 0` if that code is above the highest uploaded one. Otherwise set it to the
smallest multiple of 1,000,000 above the highest uploaded code. Check the result stays below
Play's ceiling of 2,100,000,000.

Tell the user plainly: the first release under the new scheme may jump the code sharply, and that
is permanent, because Play never accepts a lower code again.

Then show the user the plan in one message and wait for confirmation:

- the module's Gradle path and directory, the variant, package name, and bundle task
- the version name, the base, and the code the next release will get
- which existing blocks will be replaced (signing, version, and any flavor or variant API version
  overrides) and which workflow files will be added
- each ignored file CI will restore, its path, and the secret it comes from
- the release environment's name, or that the repo will use repository secrets because it can't
  have one
- the release notes file, such as `whatsnew-en-US`, and any existing release automation it
  replaces

## 3. Apply

**Gradle.** From `templates/signing-and-version.gradle.kts`, or `signing-and-version.gradle` for
Groovy:

- Add the top-level section after the `plugins` block, or after the last `apply plugin:` line in
  older Groovy files. It must come before `android { }`, which reads its values. In Kotlin DSL,
  add `import java.util.Properties` at the top of the file.
- Fill `__VERSION_NAME__` and `__VERSION_CODE_BASE__`.
- Wire the commented `android { }` fragments into the existing blocks. Merge them with what is
  there; do not create duplicate `defaultConfig` or `buildTypes` blocks.
- Remove the old `versionCode` / `versionName` assignments, including flavor and variant API
  overrides, and any old release signing, once the user has agreed to replace them.

**Gitignore.** Add `keystore.properties`.

**Wrapper.** If `gradlew` is not executable in git, run `git update-index --chmod=+x gradlew`.

**Workflow.** Copy `templates/release.yml` to `.github/workflows/release.yml` and fill in
`__JAVA_VERSION__`, `__MODULE_PATH__` (the Gradle path, with its leading colon, such as `:app`),
`__MODULE_DIR__` (the directory, such as `app`), `__BUNDLE_TASK__`, `__VARIANT__`, and
`__PACKAGE_NAME__`. Fill `__ENVIRONMENT__` with the environment's name. Without an environment,
delete that line and the comment above it. Keep the pinned commit SHAs unless the user asks to
update them.

The template has one restore step, for `google-services.json`, between the
`__RESTORE_FILES_BEGIN__` and `__RESTORE_FILES_END__` markers. Fill `__GOOGLE_SERVICES_PATH__`
with the path from step 1. For each other ignored file the release build needs, add a copy of
that step, with the secret named after the file (`secrets.properties` becomes
`SECRETS_PROPERTIES`). Then delete the two marker lines. If nothing needs restoring, delete
everything from one marker to the other.

**Release notes.** Copy `templates/whatsnew/whatsnew-en-US` to
`distribution/whatsnew/whatsnew-<locale>`, using the listing's default language from step 1,
such as `whatsnew-en-GB`.

**Docs.** Copy `templates/RELEASING.md` to the repo root and fill `__BUILD_FILE__`, `__REPO__`,
`__MODULE_PATH__`, `__BUNDLE_TASK__`, and `__ENVIRONMENT__`. Fill `__SECRET_FLAGS__` with
`-R <owner/repo> --env <environment>`, or just `-R <owner/repo>` without an environment. Then
delete the `__ENVIRONMENT_BEGIN__` and `__ENVIRONMENT_END__` marker lines, or, without an
environment, everything from one to the other. Replace `__FILE_SECRET_LINES__` with one line per
restored file, such as `gh secret set GOOGLE_SERVICES_JSON <flags> < <path>`, or delete it if
there are none. Link RELEASING.md from the README.

Nothing may be left unfilled:

```bash
grep -rnE '__[A-Z_]+__' .github/workflows/release.yml RELEASING.md <dir>/build.gradle*
```

must print nothing.

## 4. Verify

Do all of this before telling the user it works.

1. **A clean build tree.** Never build in the user's checkout. A `keystore.properties` there
   takes precedence over the environment variables, so a test build would sign with the user's
   real upload key. Build in a scratch worktree with your edits applied:
   ```bash
   git worktree add --detach <scratch>/verify HEAD
   git diff HEAD --binary | git -C <scratch>/verify apply
   ```
   Like CI, it holds only tracked files, so it also shows whether the restore list is complete.
   If `keystore.properties` is somehow there, stop and find out why.
2. **Copy in the restore list, and nothing else.** Copy each file from step 1's restore list
   from the main checkout to the same path, plus `local.properties` (or set `ANDROID_HOME`) for
   the SDK. If the build then fails over a missing file, that file belongs on the restore list:
   add its restore step and secret line as in **3. Apply**.
3. **Throwaway keystore.** In a scratch directory outside the repo:
   `keytool -genkeypair -keystore test.jks -storepass testpass -keypass testpass -alias test -keyalg RSA -keysize 2048 -validity 1 -dname CN=test`
4. **Find what the build would upload.** Run `./gradlew <path>:<bundle task> --dry-run` and look
   for upload tasks in the list it prints:
   `grep -iE 'upload|sentry|bugsnag|datadog|embrace|newrelic|instabug|appdistribution'`.
   Crashlytics adds `uploadCrashlyticsMappingFile<Variant>` when minification is on. Sentry,
   Bugsnag, and others add their own, and use tokens already in the user's environment. Pass
   each task you find to the builds below with `-x <full task path>`, so the test build pushes
   nothing into the user's real projects. Take the names from the dry run: `-x` with a task that
   does not exist fails the build.
5. **Build signed**, pointing the four environment variables at the throwaway keystore.
6. **Check the result:**
   - a bundle exists under `<dir>/build/outputs/bundle/<variant>/`, matching the workflow's glob.
     If the project moves its build directory, fix the workflow's paths to match.
   - `keytool -printcert -jarfile <the .aab>` shows the throwaway `CN=test`, proving the release
     signing config is wired
   - `./gradlew -q <path>:printVersionName | tail -n 1` prints the version name
   - the manifests AGP writes for the variant carry exactly one versionCode, the derived one:
     `find <dir>/build/intermediates -path '*<variant>*' -name AndroidManifest.xml -exec grep -ho 'android:versionCode="[0-9]*"' {} + | sort -u`.
     The packaged manifest reflects variant API overrides, and the merged one may not, so read
     them all. Any other code means an override is still in place.
   - the tag check from the workflow accepts `v<name>` and rejects any other tag, run as shell
7. **Unsigned fallback.** The same build with no signing variables set must still succeed.
8. **Scan the merged manifest for declared permissions.** Libraries add permissions too, so scan
   the merged manifest from this build rather than the source:
   `find <dir>/build/intermediates/merged_manifest -path '*<variant>*' -name AndroidManifest.xml`.
   Flag anything Play makes you declare before it commits a release: `FOREGROUND_SERVICE_*`
   types, `USE_EXACT_ALARM` / `SCHEDULE_EXACT_ALARM`, `USE_FULL_SCREEN_INTENT`,
   `ACCESS_BACKGROUND_LOCATION`, SMS and call log permissions, `QUERY_ALL_PACKAGES`,
   `MANAGE_EXTERNAL_STORAGE`, `REQUEST_INSTALL_PACKAGES`, `READ_MEDIA_IMAGES` /
   `READ_MEDIA_VIDEO`, `com.google.android.gms.permission.AD_ID` (added by Firebase Analytics
   and ad SDKs), Health Connect's `android.permission.health.*`, and services protected by
   `BIND_ACCESSIBILITY_SERVICE` or `BIND_VPN_SERVICE`. Those last two appear as
   `android:permission` on a `<service>`, not as `<uses-permission>`. This list is not complete;
   say that too.
9. **Clean up.** `git worktree remove --force <scratch>/verify` removes the worktree and the
   files copied into it. Delete the throwaway keystore.

If any check fails, fix it and run the checks again. Do not hand off a pipeline that has not
built.

## 5. Hand off

Give the user a checklist of what is left, in this order:

1. **Play service account.** Walk them through `references/play-console.md`. It has the most
   steps and a propagation delay, so it goes first.
2. **Release environment**, if the repo has one. RELEASING.md has the commands to create it,
   along with a tag ruleset that limits who can push `v*` tags. These change repository
   settings. The user runs them, or you run them after an explicit yes. The environment must
   exist before its secrets can be set.
3. **Secrets.** The commands from RELEASING.md, filled in, run by the user. Find the keystore
   path by asking, or by searching the home directory for `*.jks` / `*.keystore` outside build
   and cache directories. Skip `~/.android/debug.keystore`, which every Android developer has.
   Never run `keytool -list` yourself, because it asks for the keystore password. Always tell
   them that a filename is circumstantial evidence, and that comparing `keytool -list -v`
   fingerprints with Play Console's App integrity page is the actual check. For an app already on Play, they must never generate a new upload key.
4. **Declarations** from step 4.8, with the troubleshooting.md entry on why they fail the first
   upload. Resolving them before the first tag saves a failed run and a burned versionCode.
5. **Commit.** Offer to commit on a branch and open a PR. Do it only if they say yes.
6. **Releasing from now on.** Point to the `play-release` skill if it is installed, and to
   RELEASING.md otherwise.

State what you verified, and what you could not: nothing here has talked to Play yet. The first
real run is also the first test of the service account and secrets.
