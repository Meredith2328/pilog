# pilog write for Android — decision memo

## What it is

A thin Android package around the existing pilog write page, `tools/write.html`
(the `/write` page from PR #4). No new web app and no separate website: the
APK ships that same page offline, plus a small native bridge.

## Packaging route: Capacitor, not native Compose

| | Capacitor + write.html (chosen) | Kotlin / Compose rewrite |
|---|---|---|
| Write UX | The one already built and tested (editor, preview, front matter, PR publish) | Would have to be rebuilt and then kept in sync |
| Upstream changes | `npm run apk` repackages the current `tools/write.html` | Every change needs porting |
| Native size | One Java plugin (~250 lines) + ~450 lines of bridge JS | Whole app |
| APK | ~1 MB (R8 release) | Similar or larger |

`scripts/build-web.mjs` copies `tools/write.html` without forking it. It applies
five asserted patches: allow the bundled script in the CSP, defer boot until the
bridge is ready, use relative font paths, and expose two hooks (`open`,
`markExported`). It also makes a few copy tweaks. If write.html changes shape,
the build fails loudly rather than silently drifting.

## v1 scope

| Requirement | How |
|---|---|
| Local notes as `.md` | Drafts are mirrored to `Documents/pilog/posts/<category>/<slug>.md` with pilog front matter. Rename = change category/slug; delete removes the file. Import `.md` via the file picker. |
| Edit + preview | write.html unchanged: editor toolbar, pilog-faithful preview, card preview, all front matter fields. |
| Password vault | Separate "vault space". PBKDF2-SHA256 (310k) → AES-GCM wraps a random data key; one encrypted blob in app-private storage. Password never stored. Optional biometric unlock via a `BIOMETRIC_STRONG`-bound Keystore key. Auto-lock after 60 s in background, `FLAG_SECURE` while open, no `.md` mirror for vault notes. |
| Open PR to Meredith2328/pilog | write.html's existing flow: fine-grained PAT → `write/<date>-<slug>` branch → PR into `pilog`, never a direct push or merge. In the app the token is kept in Keystore-encrypted prefs instead of WebView storage. |
| piwiki | Disabled stub in the export sheet; enable by filling `PIWIKI` in `web/native.js` once the repo exists. |
| PC sync | Trivial only: the `Documents/pilog/posts/` folder over USB, or the per-note share sheet. No sync engine. |

## Why a fine-grained PAT, not OAuth

GitHub OAuth for a mobile app needs a registered OAuth/GitHub App (client id,
device flow or redirect handling) owned by the repo owner. That is extra
infrastructure for a single-user tool. A fine-grained PAT limited to
`Meredith2328/pilog` with only Contents + Pull requests write, with an expiry,
is the smaller-blast-radius option. PR #3 already established it, and here it
is Keystore-encrypted at rest. OAuth device flow can replace it later without
touching the publish code.

## Out of scope for v1

Two-way folder sync, image/asset upload, a piwiki publish implementation, iOS,
Play Store signing.
