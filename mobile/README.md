# pilog write — Android app

This is the pilog write page (`tools/write.html`) packaged as an offline Android
app with Capacitor. See [PRODUCT.md](PRODUCT.md) for scope and why it is built
this way. The Python site and generator are untouched; the app only reaches
`blogs/` through GitHub PRs.

```
mobile/
├── scripts/build-web.mjs   # tools/write.html + site fonts + web/ → www/ (generated)
├── scripts/smoke.mjs       # browser test of the bridge under a fake Capacitor runtime
├── web/native.js           # bridge: .md mirror, image assets, vault, Keystore token, export, piwiki stub
├── web/native.css
├── capacitor.config.json
└── android/                # Capacitor native project (+ PilogSecurePlugin.java)
```

## Build the APK

Requirements: Node 22+, JDK 21, and an Android SDK with platform 36 and build-tools 35.
Android Studio installs all of these.

```bash
cd mobile
npm install
echo "sdk.dir=$HOME/Android/Sdk" > android/local.properties   # or set ANDROID_HOME
npm run apk
# → mobile/android/app/build/outputs/apk/release/app-release.apk   (~1 MB)
```

`npm run apk` rebuilds `www/` from the current `tools/write.html`, runs
`cap sync`, then runs the platform's Gradle wrapper with `:app:assembleRelease`. The release build is
shrunk with R8 and resource shrinking, and uses the fixed signing key described
below. `npm run apk:debug` builds an unshrunk, inspectable
`apk/debug/app-debug.apk` (about 4 MB) for `chrome://inspect`. If you use
Android Studio, run `npm run sync` and then open `mobile/android`.

`www/` is generated and gitignored; there is no copy of the write UI under
`mobile/`. Any change to `tools/write.html` reaches the app the next time you run
`npm run apk` or `npm run sync`, and an installed APK keeps the version it was built with.

## Signing and GitHub builds

Local builds use `~/.android/debug.keystore`, or the file specified by
`PILOG_ANDROID_KEYSTORE`. Both release and debug APKs use that same file.
The key alias and passwords are `androiddebugkey` and `android`.
Gradle verifies its certificate against `signing-certificate.sha256` before
building. A missing key or a different certificate stops the build.

To build on another computer, copy the existing keystore there and use it via
the same path or `PILOG_ANDROID_KEYSTORE`.

The `Build Android APK` GitHub Actions workflow builds on changes to the mobile
app, write page, or bundled fonts. It restores the same keystore from the
repository secret `PILOG_ANDROID_KEYSTORE_BASE64`, verifies the signature, and
uploads the APK as the `pilog-write-apk` artifact. Download it from the run's
Artifacts section. The artifact is retained for 90 days.

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
write to `Documents/`. APKs built with the fixed key can update each other on
the same device. When switching from an APK signed with a different key,
export all notes, uninstall that version, and install the fixed-key APK.

## Using it

- **Notes**: every draft is also written to
  `Documents/pilog/posts/<category>/<slug>.md` with pilog front matter.
  If shared Documents can't be written, the app falls back to
  `Android/data/io.github.meredith2328.pilogwrite/files/pilog/`. To rename a note,
  change its category or file name in 信息. To delete one, archive it first
  (归档 on its row), open ⋯ → 查看归档文章, and tap 删除 there (it asks twice);
  to open an existing file, use ⋯ → 更多设置 → 导入 .md.
- **Export**: 导出 → 分享 / 导出 .md opens the Android share sheet.
- **PC sync**: plug in over USB and copy `Documents/pilog/posts/` into the repo's
  `blogs/posts/`. This is a one-way copy; there is no sync engine.
- **Images**: the write page keeps a local image library. Open it with the
  image button at the right edge of the format bar, or 稿件 ⋯ → 图片库; take a
  photo, pick from the gallery, paste, or drag an image in. Crop, rotate 90°,
  flip, and shrink the long edge to 2000/1600/1200/800 px, then 插入正文 writes
  `![[name]]` at the caret and 设为预览图 points the card cover at it. Images
  live in IndexedDB, the app also mirrors them to `Documents/pilog/assets/`,
  and publishing uploads the ones a draft uses to `blogs/assets/` in the same
  `write/…` branch. The vault does not support images.
- **Vault** (Android app only): open ⋯ → 更多设置 → 私密库. The first time, you
  set a password (minimum 6 characters; it can't be recovered). Vault notes are
  stored as one AES-GCM encrypted file in app-private storage and are never
  mirrored as `.md`.
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
  2. In the app, open ⋯ → 更多设置 → GitHub 令牌, paste the token, turn on
     记住, and tap 保存并验证. The token is encrypted with an Android Keystore
     key and sent only to `api.github.com`.
  3. Tap 导出 → 发布（开 PR）. The app creates a `write/<date>-<slug>` branch,
     writes `blogs/posts/<category>/<slug>.md`, and opens a PR into `pilog`.
     Review and merge it on GitHub; the app never merges.
- **Edit an online post**: 稿件 ⋯ → 编辑线上文章, then choose its directory
  and article from the cascading dropdowns. Selecting an article loads its
  original source from `pilog` into the editor.
- **piwiki**: shown as disabled until the piwiki repo exists. To enable it
  later, set `PIWIKI.repo` in `web/native.js`.

## Test

```bash
npm --prefix mobile run sync
python -m playwright install chromium
python tests/test_write.py
python tests/test_write_drafts.py
python tests/test_write_live.py
```

The browser test exports two same-day drafts to actual files, checks filename
stability and manual naming, and loads an online post through the real public
catalog and GitHub API. Screenshots and downloads are stored in `.write_live/`.
`tests/test_write.py` covers the writer itself (autosave, preview, publish/PR,
post picker) and `tests/test_write_drafts.py` covers swipe gestures plus 稿件
sorting, pinning, archiving and manual order; both start their own local server
and need Playwright's chromium.

## Changelog

### 0.4.0 (2026-10-27)

- Images: a local image library in the write page. Open it with the image
  button at the right edge of the format bar, or 稿件 ⋯ → 图片库; take a photo,
  pick from the gallery, paste, or drag images in, then crop, rotate 90°, flip,
  and shrink the long edge to 2000/1600/1200/800 px. 插入正文 writes `![[name]]`
  at the caret and 设为预览图 sets it as the card cover. Images live in
  IndexedDB, the app mirrors them to `Documents/pilog/assets/`, and publishing
  uploads the ones a draft uses to `blogs/assets/` in the same write branch.
  The vault does not support images.

### 0.3.0 (2026-10-27)

- The 稿件 panel is slimmer: a dark title bar, one top row with 新建, a compact
  排序 box that shows only the current value, a search box, and ⋯. The list is
  flat: pinned drafts stay first, archived ones are kept out of it.
- Search filters as you type and matches titles only by default; a 全文 toggle
  inside the search box also matches body, tags, and folder, and in that mode
  each matching row shows the paragraph where it matched with the keywords
  highlighted (two lines at most). It ignores case and needs every
  space-separated keyword to match. The header counts the results
  (「N 个结果」) and the box has a clear button; Esc clears the query without
  closing the panel, and switching views or reopening the panel clears it and
  returns to title search.
- Each row has 置顶 / 取消置顶 and 归档 on its right, and a pinned row now draws
  the highlight border around the whole row. ⋯ → 查看归档文章 opens the archive:
  there the top-right control is a ← back arrow instead of ⋯, and the rows
  offer 恢复 and 删除, with delete still asking twice.
- 编辑线上文章 and 更多设置 also live in the ⋯ menu. The 更多设置 sheet holds
  导入 .md, GitHub 令牌 (with status), 外观 (light/dark), 私密库 (app only),
  使用说明, and the local-storage hint.
- Sorting covers edited / created / name by pinyin / manual; manual order is set
  by long-pressing a row and dragging it up or down. 导出 / 发布（开 PR）stay in
  the write page, and the clear-all drafts button is still gone.
- Interface Chinese now uses a self-hosted pixel font, Ark Pixel 12px zh_hans
  (OFL-1.1, subset to about 165 KB). Body text and preview keep the reading
  font, and English stays Inter / JetBrains Mono.

### 0.2.6 (2026-10-27)

- Swipe left or right between 信息, 写作, and 预览: left goes to the next page,
  right goes back. A swipe that starts while the keyboard is open, or on a
  scrollable area or form control, does nothing; with the keyboard closed the
  editor itself can be swiped. Swipe down on a bottom sheet's title to close
  the sheet.
- Removed the 清空本机全部稿件 button from 稿件 and the 清空私密库全部稿件 button
  from the vault. Deleting a single draft is still there and asks for
  confirmation.
- The 稿件 list gained sorting (edited / created / name by pinyin / manual), a
  filter (all / pinned / archived), pin, archive, and grouping by category
  folder. Manual order is changed with 上移 / 下移 in the ⋯ menu at the end of
  each row, and the sort, filter, and grouping choices are remembered.

### 0.2.5

- Fix the remaining first-focus caret bug on older Android WebViews: restart
  the native input connection once the soft keyboard has resized the editor.
  If a broken IME still appends the first text at the end, detect that
  unambiguous case and move it to the visible caret before autosaving.

### 0.2.4

- First attempt at restoring the editor caret after Android keyboard resizing.

### 0.2.3

- New default filenames include a persistent six-digit suffix, such as
  `post-20261006-123456.md`, unique among local drafts.

### 0.2.2

- Press Back once for an exit prompt, then again within two seconds to exit.
- Local builds and GitHub Actions use the same verified signing key.

### 0.2.1

- 编辑线上文章 picks posts from cascading folder dropdowns (paste path moved to
  高级). Without a token it lists the blog's published posts; with a token, the
  full `blogs/posts` tree on `pilog`. The tree is fetched once per open/refresh.

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
