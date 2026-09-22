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

Find the application module and its build file:

```bash
grep -lE 'com\.android\.application|android\.application' */build.gradle* 2>/dev/null
ls settings.gradle* gradle/libs.versions.toml 2>/dev/null
```

If more than one module applies the application plugin, ask which one ships to Play. Then read
the module's build file in full and record:

| Value | Where it comes from |
| --- | --- |
| DSL | `build.gradle.kts` is Kotlin, `build.gradle` is Groovy |
| Package name | `applicationId` of the flavor that ships to Play, plus any `applicationIdSuffix` |
| Variant | flavor + `Release`, e.g. `prodRelease`; plain `release` without flavors |
| Bundle task | `bundle` + capitalized variant, e.g. `bundleProdRelease` |
| Current version | existing `versionCode` / `versionName`, and how they are computed |
| Existing signing | any `signingConfigs` block, and what the release build type uses today |
| JDK | `jvmToolchain`, `compileOptions`, or `jvmTarget`; use 17 if none says higher |
| Google Services | whether `com.google.gms.google-services` is applied, and where the variant's `google-services.json` lives (`find <module>/src -name google-services.json`) |
| Crashlytics | whether its plugin is applied, which uploads mappings during release builds |

And about the repository:

```bash
gh repo view --json nameWithOwner,defaultBranchRef,visibility
gh api repos/{owner}/{repo}/actions/permissions
gh secret list
ls .github/workflows 2>/dev/null
```

Actions must be enabled. If `allowed_actions` is not `all`, the pinned actions in the template
must be allowed explicitly; tell the user which. On a private repo, CI minutes come from the
account's quota; a release run takes roughly 5-15 minutes.

### The version question only the user can answer

Play remembers every `versionCode` ever uploaded, and the repo does not. Ask the user for the
**highest versionCode uploaded to Play** (Play Console → App bundle explorer lists them). Do not
assume it equals the build file's value: codes may have come from another branch, a manual
upload, or an old scheme.

If the app has never been uploaded to Play, the first release must be done by hand in Play
Console. Say so now; the API cannot create an app or publish to a never-published app.

## 2. Plan the version scheme and confirm

`appVersionName` must be `MAJOR.MINOR` or `MAJOR.MINOR.PATCH` with minor and patch under 100.
Keep the current name if it fits. Otherwise propose the nearest valid one and ask.

The derived code is `versionCodeBase + major * 10000 + minor * 100 + patch`. Set
`versionCodeBase = 0` if that gives a code above the highest uploaded one. Otherwise set it to the
smallest multiple of 1,000,000 above the highest uploaded code. Check the result stays below
Play's ceiling of 2,100,000,000.

Tell the user plainly: the first release under the new scheme may jump the code sharply, and that
is permanent, because Play never accepts a lower code again.

Then show the user the plan in one message and wait for confirmation:

- the module, variant, package name, and bundle task
- the version name, the base, and the code the next release will get
- which existing blocks will be replaced (signing, version) and which workflow files will be added
- whether Google Services is handled, and at which path

## 3. Apply

**Gradle.** From `templates/signing-and-version.gradle.kts`, or `signing-and-version.gradle` for
Groovy:

- Add the top-level section after the `plugins` block. In Kotlin DSL, add
  `import java.util.Properties`.
- Fill `__VERSION_NAME__` and `__VERSION_CODE_BASE__`.
- Wire the commented `android { }` fragments into the existing blocks. Merge them with what is
  there; do not create duplicate `defaultConfig` or `buildTypes` blocks.
- Remove the old `versionCode` / `versionName` assignments and any old release signing, once the
  user has agreed to replace them.

**Gitignore.** Add `keystore.properties`. If `google-services.json` is committed rather than
ignored, leave it alone and drop the restore step from the workflow; it is not a secret, and that
repo made its own choice.

**Workflow.** Copy `templates/release.yml` to `.github/workflows/release.yml` and fill in
`__JAVA_VERSION__`, `__MODULE__`, `__BUNDLE_TASK__`, `__VARIANT__`, and `__PACKAGE_NAME__`. For
Google Services, fill `__GOOGLE_SERVICES_PATH__` with the path the plugin searches for the
variant and delete the two marker comment lines. Without Google Services, delete everything from
`__GOOGLE_SERVICES_BEGIN__` through `__GOOGLE_SERVICES_END__`. Keep the pinned commit SHAs
unless the user asks to update them.

**Release notes.** Copy `templates/whatsnew/whatsnew-en-US` to
`distribution/whatsnew/whatsnew-en-US`.

**Docs.** Copy `templates/RELEASING.md` to the repo root and fill `__BUILD_FILE__`, `__REPO__`,
`__MODULE__`, and `__BUNDLE_TASK__`. Replace `__GOOGLE_SERVICES_SECRET_LINE__` with
`gh secret set GOOGLE_SERVICES_JSON -R <repo> < <path>`, or delete it. Link RELEASING.md from
the README.

Nothing may be left unfilled:

```bash
grep -rnE '__[A-Z_]+__' .github/workflows/release.yml RELEASING.md <module>/build.gradle*
```

must print nothing.

## 4. Verify

Do all of this before telling the user it works.

1. **Throwaway keystore.** In a scratch directory outside the repo:
   `keytool -genkeypair -keystore test.jks -storepass testpass -keypass testpass -alias test -keyalg RSA -keysize 2048 -validity 1 -dname CN=test`
2. **`google-services.json`**, if needed, must exist locally for the build. In a git worktree it
   will not: gitignored files only exist in the main checkout. Copy it in for the test and remove
   it afterwards.
3. **Build signed**, pointing the four environment variables at the throwaway keystore. If
   Crashlytics is applied, add `-x :<module>:uploadCrashlyticsMappingFile<Variant>` so the test
   build does not push a mapping into the user's real Firebase project.
4. **Check the result:**
   - a bundle exists under `<module>/build/outputs/bundle/<variant>/`, matching the workflow's
     glob
   - `keytool -printcert -jarfile <the .aab>` shows the throwaway `CN=test`, proving the release
     signing config is wired
   - `./gradlew -q :<module>:printVersionName | tail -n 1` prints the version name
   - the tag check from the workflow accepts `v<name>` and rejects any other tag, run as shell
5. **Unsigned fallback.** The same build with no signing variables set must still succeed.
6. **Scan the merged manifest for declared permissions.** Libraries add permissions too, so scan
   the merged manifest from this build rather than the source:
   `find <module>/build/intermediates/merged_manifest -path '*<variant>*' -name AndroidManifest.xml`.
   Flag anything Play makes you declare before it commits a release: `FOREGROUND_SERVICE_*`
   types, `USE_EXACT_ALARM` / `SCHEDULE_EXACT_ALARM`, `USE_FULL_SCREEN_INTENT`,
   `ACCESS_BACKGROUND_LOCATION`, SMS and call log permissions, `QUERY_ALL_PACKAGES`,
   `MANAGE_EXTERNAL_STORAGE`, `REQUEST_INSTALL_PACKAGES`, and `READ_MEDIA_IMAGES` /
   `READ_MEDIA_VIDEO`. This list is not complete; say that too.
7. **Clean up.** Delete the throwaway keystore and any copied `google-services.json`.

If any check fails, fix it and run the checks again. Do not hand off a pipeline that has not
built.

## 5. Hand off

Give the user a checklist of what is left, in this order:

1. **Play service account.** Walk them through `references/play-console.md`. It has the most
   steps and a propagation delay, so it goes first.
2. **Secrets.** The commands from RELEASING.md, filled in, run by the user. Find the keystore
   path by asking, or by searching the home directory for `*.jks` / `*.keystore` outside build
   and cache directories. Always tell them that a filename is circumstantial evidence, and that
   comparing `keytool -list -v` fingerprints with Play Console's App integrity page is the
   actual check. For an app already on Play, they must never generate a new upload key.
3. **Declarations** from step 4.6, with the troubleshooting.md entry on why they fail the first
   upload. Resolving them before the first tag saves a failed run and a burned versionCode.
4. **Commit.** Offer to commit on a branch and open a PR. Do it only if they say yes.
5. **Releasing from now on.** Point to the `play-release` skill if it is installed, and to
   RELEASING.md otherwise.

State what you verified, and what you could not: nothing here has talked to Play yet. The first
real run is also the first test of the service account and secrets.
