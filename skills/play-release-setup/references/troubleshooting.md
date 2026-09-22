# Troubleshooting

Every entry below happened on a real first release. Read the failed step's log
(`gh run view <id> --log-failed`) before matching against this list, and match on the actual
error text.

## Upload step

**`The caller does not have permission`, right after `Creating a new Edit`**
The key authenticated, so the key, secret, and API are fine. The service account has no access
to this app in Play Console: it was never invited, or was invited without the app attached. Fix
per play-console.md step 4, wait a few minutes, then `gh run rerun <id>`.

**`401` / `invalid_grant` / `unauthorized_client`, before any edit is created**
The key itself is wrong: a truncated secret, the wrong JSON file, a deleted key, or the Google
Play Android Developer API not enabled on the key's project.

**`You must let us know whether your app uses any Foreground Service permissions`, at `Committing
the Edit`** (or the same message for another declared permission)
The bundle uploaded but Play refuses to commit it until the declaration is filed. The catch: the
declaration form often does not appear under App content until Play has registered a bundle with
that permission, and an edit that failed to commit does not count. The way out:

1. Download the bundle from the run's artifacts: `gh run download <id>`.
2. Upload it by hand in Play Console to the internal track. That registers the permission.
3. The declaration now appears under **Monitor and improve → App content**. Complete it. For
   foreground services Play asks for a description, the impact of the task being deferred or
   interrupted, a use case, and a link to a video showing the feature being triggered.
4. Finish that release by hand, and paste the release notes: they only reach Play through the
   workflow, so the manual path has none.

That manual upload **uses up the versionCode**, so the next automated release must be a higher
version. Do not re-run the failed workflow run afterwards; it will be rejected as a duplicate.

The cheap prevention is the setup skill's manifest scan: warn the user about declarations before
the first tag, not after.

**`Only releases with status draft may be created on draft app`**
The app has never been published. Its first release has to go through Play Console by hand.

**`APK specifies a version code that has already been used` / duplicate version code**
That code is published or was uploaded by hand. Bump the version; codes are never reusable. If
the derived code is below codes published before this setup existed, `versionCodeBase` was set
too low - raise it past the highest published code. It may only ever go up.

## Before the upload

**`Tag vX.Y does not match appVersionName`**
The bump PR is not merged, or a commit that predates it got tagged. Delete the tag
(`git push origin :refs/tags/vX.Y && git tag -d vX.Y`), confirm the default branch has the bump,
re-tag the merge commit.

**`File google-services.json is missing`**
The `GOOGLE_SERVICES_JSON` secret is missing or empty, or the workflow writes it to a path the
Google Services plugin does not search for this variant. The plugin's error lists every path it
tried; the restore step must write to one of them.

**Signing fails with a keystore or key password error**
`KEYSTORE_PASSWORD` or `KEY_PASSWORD` is wrong. They are often identical: for a PKCS12 keystore
they must be. To test a JKS locally without changing it,
`keytool -certreq -alias <alias> -keystore <file> > /dev/null` asks for the key password only if
it differs from the store password. Never pass passwords as keytool flags; they land in shell
history.

## After a successful upload

**The release does not show up for a tester**
Publishing to internal testing is not enough: the tester's account must be on the track's tester
list and must accept the opt-in link from the **Testers** tab. Also check **Publishing
overview** - with managed publishing on, approved changes wait for an explicit **Publish
changes**.

**Release notes are missing**
The release went out by hand. Notes reach Play only through the workflow's `whatsNewDirectory`.

## Local gotchas

**`app/src/<flavor>/google-services.json: no such file or directory` when setting secrets**
Git worktrees do not contain gitignored files. Run secret commands from the main checkout, or use
an absolute path into it.

**A value written to `$GITHUB_ENV` is not visible**
`$GITHUB_ENV` only affects later steps, never the step that writes it. Use `export` within one
step.
