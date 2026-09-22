# Play Console and Google Cloud setup

The steps the user performs by hand to let CI upload. They involve credentials, so the agent
explains them and the user runs them; the agent never creates keys or enters secrets.

**Last verified: August 2026.** The Play Console UI moves often, and navigation paths here have
already been wrong once. If the user reports that a menu item does not exist, stop repeating
these directions: search the official docs
(https://developers.google.com/android-publisher/getting_started) and give them the current path.
The Play Console search box at the top of every page is a reliable fallback for any named page.

## 1. Pick a Google Cloud project

Any project works. If the app uses Firebase, its Firebase project already is a Google Cloud
project, and reusing it avoids creating a second. The `project_id` in `google-services.json`
names it.

Linking the Cloud project to the Play developer account is **no longer required**. Older guides,
and older model knowledge, send people to "Setup → API access" to link it; that page may not
exist for their account.

## 2. Enable the API

https://console.cloud.google.com/apis/library/androidpublisher.googleapis.com, with the project
selected → **Enable**. Skipping this surfaces later as a 403 that looks like a permissions
problem.

## 3. Create the service account and its key

https://console.cloud.google.com/iam-admin/serviceaccounts, same project.

- **Create service account**, or on the Credentials page **Create credentials → Service
  account**. Not "API key" and not "OAuth client ID" - neither can authenticate uploads.
- Name it something like `play-release-uploader`. Skip the optional project role steps; Google
  Cloud roles do not grant Play access.
- The key is a separate step: click the account's **email address** to open it → **Keys** tab →
  **Add key → Create new key → JSON**. The file downloads immediately and cannot be downloaded
  again. Users regularly stop after creating the account and wonder where the file is.

Copy the account's email address; step 4 needs it.

## 4. Grant it access in Play Console

https://play.google.com/console/users-and-permissions → **Invite new users** → the service
account email → **App permissions** tab → **Add app** → the app → grant **Release manager**, or
at minimum **Release apps to testing tracks** → **Invite user**.

The grant must be on the **app**, not only the account. An account-level invite with no app
attached fails exactly like no invite at all. Service accounts do not need to accept anything.
Allow a few minutes to propagate before the first run.

## 5. Store the key and delete the download

The user sets the `PLAY_SERVICE_ACCOUNT_JSON` secret from the file, then deletes the file. It is
a live credential to their Play account and has no reason to stay in Downloads.

## Before the first automated upload

- **The app must already exist in Play Console with at least one release uploaded by hand.**
  The API cannot create an app, and a never-published app only accepts draft releases.
- **Sensitive permission declarations** - foreground services, exact alarms, full-screen intents,
  background location, and so on - have to be completed under **Monitor and improve → App
  content** before Play commits a release that uses them. The form for a newly added permission
  only appears after Play has registered a bundle containing it. See troubleshooting.md.
