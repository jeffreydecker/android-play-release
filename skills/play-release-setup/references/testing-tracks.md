# Sending a release to specific testers

The workflow uploads to the tracks listed in `distribution/tracks`, `internal` by default. This
file covers how Play decides who sees a release on a track, and how to give a release to a
narrower group than the whole internal tester list.

**Last verified: November 2026**, against Play Console Help ("Set up an open, closed, or internal
test" and "Share app bundles and APKs internally"). If the console differs, search those pages
for the current wording rather than repeating these directions.

## How Play picks the audience

The audience belongs to the **track**, not to the release. A tester who is on a track's lists
and has accepted its opt-in link gets whatever release is on that track. There is no way to
point one upload at a subset of a track's testers. So "release this build to Alice and Bob" means
"upload it to a track whose testers are Alice and Bob".

| | Internal testing | Closed testing |
| --- | --- | --- |
| Testers come from | email lists | email lists or Google Groups |
| Size | up to 100 testers per app | up to 50 lists per track, 2,000 testers per list; Groups have no size limit |
| Tracks | exactly one | the default closed track (`alpha` in the API) plus any you create |
| Review | might skip standard policy and security review, so builds arrive in minutes | expect Play's review before testers get it |

Two rules catch people out:

- **A user who opts into internal testing is not eligible for closed or open tests.** Put someone
  on the internal list and they stop receiving closed-track builds for that app. Keep each
  person on one track.
- **Track names come from Play Console.** The API name of a track you create is the name you gave
  it there. `distribution/tracks` must match it exactly.

## Choosing an approach

**Everyone on the internal list should get it.** Nothing to do. That is the default.

**The internal list itself is the wrong group.** Change which email lists the internal track
uses in Play Console: **Test and release → Testing → Internal testing → Testers**. That changes
the audience for every later internal release too.

**Different groups get different releases.** This is what `distribution/tracks` is for. Give
each group its own closed testing track, once, by hand:

1. **Test and release → Testing → Closed testing → Create track.** Name it for the group, such as
   `qa` or `design-review`. Lowercase with hyphens avoids surprises.
2. In the track's **Testers** tab, select the email lists or Google Groups for that group, and
   copy the opt-in link. Each tester opens it once and accepts.
3. Release to it by putting its name in `distribution/tracks` in the version bump PR. Several
   lines upload the same build to several tracks in one edit.

The service account's **Release apps to testing tracks** permission covers closed tracks, so
nothing changes in play-console.md. The workflow refuses `production`, `beta` (open testing,
which anyone can join) and `internalsharing`.

**One build, a few people, right now, with no versionCode spent.** That is internal app sharing,
which this pipeline does not automate. Uploading a bundle there gives a download link for up to
100 people, valid for 60 days. Version codes need not be new, and Play re-signs the build with
its own internal sharing key. Recipients must first enable **Internal app sharing** in the Play
Store app (**Settings → About**, tap **Play Store version** seven times, then turn on the
toggle). Shared builds cannot be promoted to any track. Upload by hand on Play Console's
**Internal app sharing** page (the console's search box finds it).

## Giving an already uploaded build to another group

Do not re-tag or re-run: the versionCode is used up, and a new upload of it is rejected. Promote
the existing release in Play Console from its track to the other one. Change
`distribution/tracks` in the next bump PR if the next release should go there too.
