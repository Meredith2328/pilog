# pilog write — Android app

This is the pilog write page (`tools/write.html`) packaged as an offline Android
app with Capacitor. See [PRODUCT.md](PRODUCT.md) for scope and why it is built
this way. The Python site and generator are untouched; the app only reaches
`blogs/` through GitHub PRs.

```
mobile/
├── scripts/build-web.mjs   # tools/write.html + site fonts + web/ → www/ (generated)
├── scripts/smoke.mjs       # browser test of the bridge under a fake Capacitor runtime
├── web/native.js           # bridge: .md mirror, vault, Keystore token, export, piwiki stub
├── web/native.css
├── capacitor.config.json
└── android/                # Capacitor native project (+ PilogSecurePlugin.java)
```

## Build the debug APK

Requirements: Node 22+, JDK 21, and an Android SDK with platform 36 and build-tools 36.
Android Studio installs all of these.

```bash
cd mobile
npm install
echo "sdk.dir=$HOME/Android/Sdk" > android/local.properties   # or set ANDROID_HOME
npm run apk
# → mobile/android/app/build/outputs/apk/release/app-release.apk   (~1 MB)
```

`npm run apk` rebuilds `www/` from the current `tools/write.html`, runs
`cap sync`, then runs `./gradlew assembleRelease`. The release build is
shrunk with R8 and resource shrinking, and is signed with the local debug key
so it installs directly. `npm run apk:debug` builds an unshrunk, inspectable
`apk/debug/app-debug.apk` (about 4 MB) for `chrome://inspect`. If you use
Android Studio, run `npm run sync` and then open `mobile/android`.

## Install

- USB: enable Developer options and USB debugging on the phone, then run
  `adb install -r mobile/android/app/build/outputs/apk/release/app-release.apk`.
- Without a computer: copy `app-release.apk` to the phone, open it in Files, and
  allow "install unknown apps" for Files when Android asks.

The package is `io.github.meredith2328.pilogwrite` and needs Android 8.0 (API 26)
or newer, with an up-to-date Android System WebView (Chrome 90+; the Play Store
updates it automatically). On a device whose WebView was never updated, for
example Chrome 74 on a stock Android 10 image, everything still works, but
parts of write.html's layout (`min()`/`max()` padding, flex `gap`) degrade.
On Android 8–10, the first save asks for storage permission so the app can
write to `Documents/`. Both APKs are signed with the local debug key, so an APK built on a
different machine won't install over it. Uninstall the old one first, after
exporting your notes.

## Using it

- **Notes**: every draft is also written to
  `Documents/pilog/posts/<category>/<slug>.md` with pilog front matter.
  If shared Documents can't be written, the app falls back to
  `Android/data/io.github.meredith2328.pilogwrite/files/pilog/`. To rename a note,
  change its category or file name in 信息; to delete it, use 稿件 → 删除. To
  open an existing file, use 稿件 → 导入 .md.
- **Export**: 导出 → 分享 / 导出 .md opens the Android share sheet.
- **PC sync**: plug in over USB and copy `Documents/pilog/posts/` into the repo's
  `blogs/posts/`. This is a one-way copy; there is no sync engine.
- **Vault**: 稿件 → 进入私密库. The first time, you set a password (minimum 6
  characters; it can't be recovered). Vault notes are stored as one AES-GCM
  encrypted file in app-private storage and are never mirrored as `.md`.
  - Lock with the lock button in the top bar. The vault also locks itself after
    60 s in the background.
  - Screenshots are blocked while the vault is open.
  - Inside the vault you can move notes in from the normal list (their `.md`
    file is deleted), change the password, and turn fingerprint/face unlock on
    or off.
- **Publish to pilog** (owner only):
  1. Create a GitHub fine-grained token with resource owner `Meredith2328`,
     only the `Meredith2328/pilog` repository, and `Contents` and
     `Pull requests` set to Read and write. Set an expiry.
  2. In the app, open 稿件 → GitHub 令牌, paste the token, turn on 记住, and
     tap 保存并验证. The token is encrypted with an Android Keystore key and
     sent only to `api.github.com`.
  3. Tap 导出 → 发布（开 PR）. The app creates a `write/<date>-<slug>` branch,
     writes `blogs/posts/<category>/<slug>.md`, and opens a PR into `pilog`.
     Review and merge it on GitHub; the app never merges.
- **piwiki**: shown as disabled until the piwiki repo exists. To enable it
  later, set `PIWIKI.repo` in `web/native.js`.

## Test

```bash
cd mobile && npm run web
npm i --no-save playwright && npx playwright install chromium
node scripts/smoke.mjs
```

The smoke test runs the bundled page in Chromium with fake Filesystem, Share, and
PilogSecure plugins, and a mocked GitHub API. It checks the `.md` mirror,
rename and delete, export, Keystore token routing, PR publish, vault
encryption, lock and unlock, wrong password, and move into the vault. Set
`SHOTS=<dir>` to also save screenshots.

`npm run smoke` rebuilds `www/` and runs the smoke test.

## Changelog

### 0.2.0

- Native look and feel:
  - The launcher icon and splash use write's pixel dino (an adaptive icon, a
    themed/monochrome icon on Android 13+, and a dark splash variant).
    Capacitor's stock images are gone.
  - The splash stays up until the editor has painted, so launch never shows a
    blank or half-built page.
  - The status bar, navigation bar, and window background follow write's own
    light/dark toggle, and the choice is remembered for the next cold start.
- Vault: the editor stays hidden until the lock screen is passed. The lock
  screen uses the write brand block and pixel lock.
- App-specific copy: the help sheet explains the `.md` folder, the vault, and
  PR setup. The token sheet now says Keystore instead of browser storage.
- Size and speed: the default build is an R8-minified release (about 1 MB,
  down from about 5 MB). Duplicate variable-font files are deduplicated, and
  only English and Chinese resources are kept.
- Fix: in minified builds, R8 stripped Capacitor's plugin permission metadata,
  so on Android 8–10 writing to `Documents/` hung. Keep rules are added in
  `proguard-rules.pro`.

## Changelog

### 0.1.0

- Capacitor 8 Android app (min SDK 26, target 36) that ships `tools/write.html`
  offline, built from source by `scripts/build-web.mjs` without forking it.
- Drafts are mirrored as pilog-compatible `.md` files under `Documents/pilog/posts/`,
  following renames and deletes.
- Password vault: PBKDF2-SHA256 (310k) plus AES-GCM, with optional
  `BIOMETRIC_STRONG` Keystore unlock, 60 s auto-lock, `FLAG_SECURE`, and
  move-in from normal notes.
- The GitHub token is stored in Keystore-encrypted prefs instead of WebView
  storage. The publish flow is unchanged: `write/…` branch plus a PR into `pilog`.
- Export goes through the native share sheet; external links open in the system
  browser.
- piwiki publish target is present as a disabled stub.
- Defaults: app id `io.github.meredith2328.pilogwrite`; `allowBackup=false`
  (the `.md` folder is the backup); auto-lock after 60 s; minimum password
  length 6.
