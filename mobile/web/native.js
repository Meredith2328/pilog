/* pilog write — Android bridge.
   Loaded before tools/write.html's main script, which the build defers into
   window.__pilogMain. write.html keeps using localStorage synchronously; this
   file reroutes a few keys underneath it:
     - notes space: drafts stay in WebView storage and every draft is mirrored
       to Documents/pilog/posts/<category>/<slug>.md (the durable, exportable copy);
     - vault space: pilog.write.* keys live only in memory while unlocked and are
       persisted as one AES-GCM blob; the key is derived from the password with
       PBKDF2 (never stored) or released by a biometric-bound Keystore key;
     - the GitHub token (pilog.write.ghToken) goes to Keystore-encrypted prefs. */
(function () {
  "use strict";

  var Cap = window.Capacitor;
  var P = (Cap && Cap.Plugins) || {};
  var isNative = !!(Cap && Cap.isNativePlatform && Cap.isNativePlatform());
  var FS = isNative ? P.Filesystem : null;
  var Share = isNative ? P.Share : null;
  var Sec = isNative ? P.PilogSecure : null;

  var PFX = "pilog.write.";
  var TOKEN = PFX + "ghToken";
  var APP = "pilog.app.";
  var SPACE = APP + "space";
  var MIRROR_ROOT = "pilog";
  var VAULT_FILE = "vault/vault.json";
  var KDF_ITER = 310000;
  var AUTOLOCK_MS = 60 * 1000;
  /* piwiki has no public repo yet; publishing stays disabled until this is filled in. */
  var PIWIKI = { repo: "", base: "main", dir: "" };

  var S = Storage.prototype, rawGet = S.getItem, rawSet = S.setItem, rawDel = S.removeItem;
  var LS = window.localStorage, SS = window.sessionStorage;
  function lget(k) { return rawGet.call(LS, k); }
  function lset(k, v) { rawSet.call(LS, k, v); }
  function ldel(k) { rawDel.call(LS, k); }

  var space = rawGet.call(SS, SPACE) === "vault" ? "vault" : "notes";
  if (space === "vault") document.documentElement.classList.add("is-vault", "is-locked");
  var vaultMem = null;
  var tokenLocal = "";

  function routed(k) { return typeof k === "string" && k.indexOf(PFX) === 0; }
  S.getItem = function (k) {
    if (this === LS && k === TOKEN) return tokenLocal || null;
    if (this === LS && vaultMem && routed(k)) return vaultMem.has(k) ? vaultMem.get(k) : null;
    return rawGet.call(this, k);
  };
  S.setItem = function (k, v) {
    v = String(v);
    if (this === LS && k === TOKEN) { tokenLocal = v; secureSet(TOKEN, v); return; }
    if (this === LS && vaultMem && routed(k)) { vaultMem.set(k, v); vaultDirty(); return; }
    rawSet.call(this, k, v);
    if (this === LS && space === "notes") noteChanged(k, v);
  };
  S.removeItem = function (k) {
    if (this === LS && k === TOKEN) { tokenLocal = ""; secureSet(TOKEN, ""); return; }
    if (this === LS && vaultMem && routed(k)) { vaultMem.delete(k); vaultDirty(); return; }
    rawDel.call(this, k);
    if (this === LS && space === "notes") noteChanged(k, null);
  };

  /* ================= helpers ================= */
  function $(s, r) { return (r || document).querySelector(s); }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function toast(msg) {
    var t = $("#toast");
    if (!t) return;
    t.textContent = msg; t.classList.add("is-on");
    clearTimeout(toast.t); toast.t = setTimeout(function () { t.classList.remove("is-on"); }, 2400);
  }
  function api() { return window.__pilogWrite; }
  function b64(bytes) {
    var bin = "";
    for (var i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(bin);
  }
  function unb64(s) {
    var bin = atob(s), out = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }
  var DINO = ["........########", ".......##.######", ".......#########", ".......#########",
    ".......#####....", ".......#######..", "#.....#####.....", "#....########...",
    "##..######.#....", "##########......", ".#########......", "..#######.......",
    "...##..##.......", "...#....#.......", "...##...##......"];
  function dinoSvg() {
    var d = "";
    DINO.forEach(function (row, y) {
      row.replace(/#+/g, function (run, x) { d += "M" + x + " " + y + "h" + run.length + "v1h-" + run.length + "z"; });
    });
    return '<svg viewBox="0 0 16 15" shape-rendering="crispEdges" aria-hidden="true"><path fill="currentColor" d="' + d + '"/></svg>';
  }
  function el(html) { var d = document.createElement("div"); d.innerHTML = html.trim(); return d.firstChild; }

  /* ================= secure prefs (token) ================= */
  function secureGet(k) {
    if (!Sec) return Promise.resolve(lget(APP + "plain." + k) || "");
    return Sec.get({ key: k }).then(function (r) { return (r && r.value) || ""; }, function () { return ""; });
  }
  function secureSet(k, v) {
    if (!Sec) { if (v) lset(APP + "plain." + k, v); else ldel(APP + "plain." + k); return Promise.resolve(); }
    return (v ? Sec.set({ key: k, value: v }) : Sec.remove({ key: k })).catch(function () {
      toast("令牌无法写入安全存储");
    });
  }
  function loadToken() {
    var legacy = lget(TOKEN);
    if (legacy) { ldel(TOKEN); tokenLocal = legacy; return secureSet(TOKEN, legacy); }
    return secureGet(TOKEN).then(function (v) { if (!tokenLocal) tokenLocal = v; });
  }

  /* ================= notes space: mirror drafts as .md files ================= */
  var mirror = {
    dir: FS ? "DOCUMENTS" : "",
    map: JSON.parse(lget(APP + "mirror") || "{}"),
    queue: {},
    ready: false,
    timer: 0
  };
  function saveMap() { lset(APP + "mirror", JSON.stringify(mirror.map)); }
  function noteChanged(k, v) {
    var m = /^pilog\.write\.d\.(.+)$/.exec(k);
    if (!m || !FS) return;
    mirror.queue[m[1]] = v;
    clearTimeout(mirror.timer);
    mirror.timer = setTimeout(flushMirror, 300);
  }
  function mirrorPath(d, id) {
    var p = api().pathOf(d).replace(/^blogs\//, "");
    for (var other in mirror.map) {
      if (other !== id && mirror.map[other] === MIRROR_ROOT + "/" + p) return MIRROR_ROOT + "/" + p.replace(/\.md$/, "~" + id.slice(-4) + ".md");
    }
    return MIRROR_ROOT + "/" + p;
  }
  function fsWrite(path, data) {
    return FS.writeFile({ path: path, data: data, directory: mirror.dir, encoding: "utf8", recursive: true });
  }
  function fsDelete(path) {
    return FS.deleteFile({ path: path, directory: mirror.dir }).catch(function () { /* already gone */ });
  }
  function writeOne(id, json) {
    var old = mirror.map[id];
    if (json == null) {
      delete mirror.map[id]; saveMap();
      return old ? fsDelete(old) : Promise.resolve();
    }
    var d;
    try { d = JSON.parse(json); } catch (e) { return Promise.resolve(); }
    var isEmpty = !String(d.title || "").trim() && !String(d.body || "").trim();
    if (isEmpty) return old ? writeOne(id, null) : Promise.resolve();
    var path = mirrorPath(d, id);
    return fsWrite(path, api().buildOf(d)).then(function () {
      mirror.map[id] = path; saveMap();
      if (old && old !== path) return fsDelete(old);
    });
  }
  function flushMirror() {
    if (!mirror.ready) return Promise.resolve();
    var q = mirror.queue; mirror.queue = {};
    return Object.keys(q).reduce(function (p, id) {
      return p.then(function () { return writeOne(id, q[id]); });
    }, Promise.resolve()).catch(function (e) {
      if (mirror.dir === "DOCUMENTS") {
        mirror.dir = "EXTERNAL"; lset(APP + "mirrorDir", "EXTERNAL");
        Object.assign(mirror.queue, q);
        return flushMirror();
      }
      toast("同步 .md 文件失败：" + (e && e.message || e));
    });
  }
  function reconcileMirror() {
    if (!FS) return;
    mirror.dir = lget(APP + "mirrorDir") || mirror.dir;
    mirror.ready = true;
    var idx = JSON.parse(lget(PFX + "index") || "{}");
    var ids = idx.ids || [];
    Object.keys(mirror.map).forEach(function (id) { if (ids.indexOf(id) < 0) mirror.queue[id] = null; });
    ids.forEach(function (id) { mirror.queue[id] = lget(PFX + "d." + id); });
    flushMirror().then(showMirrorDir);
  }
  function showMirrorDir() {
    var n = $("#app-mirror-dir");
    if (n) n.textContent = (mirror.dir === "EXTERNAL" ? "Android/data/…/files/" : "Documents/") + MIRROR_ROOT + "/posts/";
  }

  /* ================= vault crypto ================= */
  var vault = { dek: null, file: null, timer: 0, hiddenAt: 0 };
  var enc = new TextEncoder(), dec = new TextDecoder();
  function rand(n) { return crypto.getRandomValues(new Uint8Array(n)); }
  function kek(password, salt, iter) {
    return crypto.subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveKey"]).then(function (base) {
      return crypto.subtle.deriveKey({ name: "PBKDF2", hash: "SHA-256", salt: salt, iterations: iter },
        base, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
    });
  }
  function aesKey(raw) { return crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["encrypt", "decrypt"]); }
  function seal(key, bytes) {
    var iv = rand(12);
    return crypto.subtle.encrypt({ name: "AES-GCM", iv: iv }, key, bytes).then(function (ct) {
      return { iv: b64(iv), ct: b64(new Uint8Array(ct)) };
    });
  }
  function unseal(key, box) {
    return crypto.subtle.decrypt({ name: "AES-GCM", iv: unb64(box.iv) }, key, unb64(box.ct)).then(function (pt) {
      return new Uint8Array(pt);
    });
  }
  function readVault() {
    if (!FS) return Promise.resolve(JSON.parse(lget(APP + "vault") || "null"));
    return FS.readFile({ path: VAULT_FILE, directory: "DATA", encoding: "utf8" })
      .then(function (r) { return JSON.parse(r.data); }, function () { return null; });
  }
  function writeVault(obj) {
    var text = JSON.stringify(obj);
    if (!FS) { lset(APP + "vault", text); return Promise.resolve(); }
    var tmp = VAULT_FILE + ".tmp";
    return FS.writeFile({ path: tmp, data: text, directory: "DATA", encoding: "utf8", recursive: true }).then(function () {
      return FS.rename({ from: tmp, to: VAULT_FILE, directory: "DATA", toDirectory: "DATA" });
    });
  }
  function wrapDek(password, dek) {
    var salt = rand(16);
    return kek(password, salt, KDF_ITER).then(function (k) { return seal(k, dek); }).then(function (box) {
      return { salt: b64(salt), iter: KDF_ITER, box: box };
    });
  }
  function unwrapDek(password, wrap) {
    return kek(password, unb64(wrap.salt), wrap.iter).then(function (k) { return unseal(k, wrap.box); });
  }
  function sealData(dek) {
    var obj = {};
    vaultMem.forEach(function (v, k) { obj[k] = v; });
    return aesKey(dek).then(function (k) { return seal(k, enc.encode(JSON.stringify(obj))); });
  }
  function vaultDirty() {
    clearTimeout(vault.timer);
    vault.timer = setTimeout(flushVault, 400);
  }
  function flushVault() {
    clearTimeout(vault.timer);
    if (!vaultMem || !vault.dek) return Promise.resolve();
    return sealData(vault.dek).then(function (box) {
      vault.file.data = box;
      return writeVault(vault.file);
    }).catch(function (e) { toast("私密库保存失败：" + (e && e.message || e)); });
  }
  function unlockWith(dek) {
    return aesKey(dek).then(function (k) { return unseal(k, vault.file.data); }).then(function (pt) {
      var obj = JSON.parse(dec.decode(pt));
      vaultMem = new Map(Object.keys(obj).map(function (k) { return [k, obj[k]]; }));
      vault.dek = dek;
    });
  }
  function createVault(password) {
    var dek = rand(32);
    vaultMem = new Map();
    return wrapDek(password, dek).then(function (wrap) {
      vault.dek = dek;
      vault.file = { v: 1, wrap: wrap, bio: false, data: null };
      return flushVault();
    });
  }

  /* ================= space switching ================= */
  function enterVault() { rawSet.call(SS, SPACE, "vault"); location.reload(); }
  function leaveVault() {
    flushVault().then(function () {
      call("setSecure", { on: false });
      rawDel.call(SS, SPACE); location.reload();
    });
  }
  function lockVault() {
    flushVault().then(function () { vaultMem = null; vault.dek = null; location.reload(); });
  }

  /* ================= vault gate (lock screen) ================= */
  function gate() {
    return new Promise(function (resolve) {
      readVault().then(function (file) {
        vault.file = file;
        var fresh = !file;
        var root = el('<div class="vgate" role="dialog" aria-modal="true" aria-labelledby="vg-t">' +
          '<div class="vgate-in"><div class="vgate-brand"><span class="pix">' + dinoSvg() + '</span><span class="brand-t">PILOG·VAULT</span></div>' +
          '<div class="vgate-box">' +
          '<div class="vgate-h"><span class="vgate-lock" aria-hidden="true"></span><span id="vg-t">私密库</span><small>' +
          (fresh ? "首次使用 · 设置密码" : "已加密 · 输入密码解锁") + "</small></div>" +
          '<div class="fld"><label class="lbl" for="vg-pw">密码 <small>至少 6 位 · 无法找回</small></label>' +
          '<input class="inp mono" id="vg-pw" type="password" autocomplete="off" autocapitalize="none" spellcheck="false" enterkeyhint="done"></div>' +
          (fresh ? '<div class="fld"><label class="lbl" for="vg-pw2">再输一次</label>' +
            '<input class="inp mono" id="vg-pw2" type="password" autocomplete="off" autocapitalize="none" spellcheck="false" enterkeyhint="done"></div>' : "") +
          '<div class="vg-msg" id="vg-msg"></div>' +
          '<button class="pbtn primary block" type="button" id="vg-go">' + (fresh ? "创建私密库" : "解锁") + "</button>" +
          (!fresh && file.bio && Sec ? '<button class="pbtn block" type="button" id="vg-bio" style="margin-top:12px">用指纹 / 面容解锁</button>' : "") +
          '<button class="pbtn block" type="button" id="vg-back" style="margin-top:12px">返回普通稿件</button>' +
          '<p class="note">私密库的稿件只以加密形式保存在 App 私有目录，不会同步成 .md 文件。密码不保存在任何地方；忘记密码将无法恢复内容。</p>' +
          "</div></div></div>");
        document.body.appendChild(root);
        markReady();
        var pw = $("#vg-pw", root), msg = $("#vg-msg", root), go = $("#vg-go", root);
        function fail(t) { msg.textContent = t; msg.className = "vg-msg is-bad"; go.disabled = false; }
        function done() {
          call("setSecure", { on: true });
          document.documentElement.classList.remove("is-locked");
          root.remove(); resolve();
        }
        function submit() {
          var v = pw.value;
          if (v.length < 6) return fail("密码至少 6 位。");
          go.disabled = true; msg.className = "vg-msg"; msg.textContent = fresh ? "正在创建…" : "正在解锁…";
          if (fresh) {
            if (v !== $("#vg-pw2", root).value) return fail("两次输入的密码不一致。");
            createVault(v).then(done, function (e) { fail("创建失败：" + (e && e.message || e)); });
          } else {
            unwrapDek(v, file.wrap).then(unlockWith).then(done, function () { fail("密码不对。"); });
          }
        }
        go.addEventListener("click", submit);
        root.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.isComposing) submit(); });
        $("#vg-back", root).addEventListener("click", function () { rawDel.call(SS, SPACE); location.reload(); });
        var bio = $("#vg-bio", root);
        function tryBio() {
          msg.className = "vg-msg"; msg.textContent = "";
          Sec.bioUnlock({ title: "解锁私密库" }).then(function (r) { return unlockWith(unb64(r.secret)); })
            .then(done, function (e) { fail((e && e.message) || "生物识别未通过，请输入密码。"); });
        }
        if (bio) { bio.addEventListener("click", tryBio); tryBio(); } else setTimeout(function () { pw.focus(); }, 80);
      });
    });
  }

  /* ================= injected UI ================= */
  function injectNotesUi() {
    var anchor = $("#btn-wipe");
    if (!anchor) return;
    anchor.parentNode.insertBefore(el('<div><div class="sub">私密库</div>' +
      '<button class="pbtn block" type="button" id="app-vault">进入私密库（密码锁）</button></div>'), anchor);
    $("#app-vault").addEventListener("click", enterVault);
  }
  function injectVaultUi() {
    document.documentElement.classList.add("is-vault");
    var bar = $(".bar"), brand = $("#brand");
    if (bar && brand) {
      var lock = el('<button class="sq vlock" type="button" id="app-lock" aria-label="锁定私密库" title="锁定私密库"></button>');
      brand.insertAdjacentElement("afterend", lock);
      lock.addEventListener("click", lockVault);
      var t = $(".brand-t", brand);
      if (t) t.textContent = "VAULT";
    }
    var anchor = $("#btn-wipe");
    if (anchor) anchor.textContent = "清空私密库全部稿件";
    var list = $("#draft-list");
    if (!list) return;
    var box = el('<div><div class="sub">私密库</div>' +
      '<button class="pbtn block" type="button" id="app-move">从普通稿件移入…</button>' +
      '<div id="app-move-list"></div>' +
      '<div class="two" style="margin-top:12px"><button class="pbtn block" type="button" id="app-bio"></button>' +
      '<button class="pbtn block" type="button" id="app-pw">修改密码</button></div>' +
      '<div id="app-pw-box" hidden><div class="fld" style="margin-top:12px"><label class="lbl" for="app-pw-old">当前密码</label>' +
      '<input class="inp mono" id="app-pw-old" type="password" autocomplete="off"></div>' +
      '<div class="fld"><label class="lbl" for="app-pw-new">新密码 <small>至少 6 位</small></label>' +
      '<input class="inp mono" id="app-pw-new" type="password" autocomplete="off"></div>' +
      '<button class="pbtn primary block" type="button" id="app-pw-go">保存新密码</button></div>' +
      '<div class="two" style="margin-top:12px"><button class="pbtn primary block" type="button" id="app-leave">锁定并返回普通稿件</button></div>' +
      "</div>");
    list.parentNode.insertBefore(box, list.nextSibling);
    $("#app-leave").addEventListener("click", leaveVault);
    $("#app-move").addEventListener("click", renderMoveList);
    $("#app-move-list").addEventListener("click", function (e) {
      var b = e.target.closest("[data-move]");
      if (b) moveIn(b.dataset.move);
    });
    syncBioBtn();
    $("#app-bio").addEventListener("click", toggleBio);
    $("#app-pw").addEventListener("click", function () { var b = $("#app-pw-box"); b.hidden = !b.hidden; });
    $("#app-pw-go").addEventListener("click", changePassword);
  }
  function syncBioBtn() {
    var b = $("#app-bio");
    if (!b) return;
    if (!Sec) { b.disabled = true; b.textContent = "指纹解锁（仅 App）"; return; }
    b.textContent = vault.file.bio ? "关闭指纹解锁" : "开启指纹解锁";
  }
  function toggleBio() {
    var on = !vault.file.bio;
    var p = on
      ? Sec.bioStatus().then(function (s) {
        if (!s.available) throw new Error("这台设备没有可用的强生物识别");
        return Sec.bioEnroll({ secret: b64(vault.dek), title: "开启指纹解锁" });
      })
      : Sec.bioClear();
    p.then(function () {
      vault.file.bio = on; syncBioBtn();
      return flushVault();
    }).then(function () { toast(on ? "已开启生物识别解锁" : "已关闭生物识别解锁"); },
      function (e) { toast((e && e.message) || "操作未完成"); });
  }
  function changePassword() {
    var a = $("#app-pw-old").value, b = $("#app-pw-new").value;
    if (b.length < 6) { toast("新密码至少 6 位"); return; }
    unwrapDek(a, vault.file.wrap).then(function () { return wrapDek(b, vault.dek); }).then(function (wrap) {
      vault.file.wrap = wrap;
      return flushVault();
    }).then(function () {
      $("#app-pw-old").value = $("#app-pw-new").value = ""; $("#app-pw-box").hidden = true;
      toast("密码已修改");
    }, function () { toast("当前密码不对"); });
  }
  function plainIndex() { return JSON.parse(lget(PFX + "index") || '{"active":null,"ids":[]}'); }
  function renderMoveList() {
    var idx = plainIndex();
    var rows = idx.ids.map(function (id) {
      var d; try { d = JSON.parse(lget(PFX + "d." + id)); } catch (e) { d = null; }
      if (!d) return "";
      var t = String(d.title || "").trim() || String(d.body || "").trim().split("\n")[0].slice(0, 40) || "无标题稿件";
      return '<div class="drow"><span class="drow-main" style="cursor:default"><span class="drow-t">' + esc(t) +
        '</span><span class="drow-m"><span>posts/' + esc(d.category || "") + "</span></span></span>" +
        '<button class="drow-del" type="button" data-move="' + esc(id) + '">移入</button></div>';
    }).join("");
    $("#app-move-list").innerHTML = rows || '<p class="note">普通稿件里没有可移入的稿件。</p>';
  }
  function moveIn(id) {
    var json = lget(PFX + "d." + id);
    if (!json) return;
    vaultMem.set(PFX + "d." + id, json);
    api().open(id);
    var idx = plainIndex();
    idx.ids = idx.ids.filter(function (x) { return x !== id; });
    if (idx.active === id) idx.active = idx.ids[0] || null;
    lset(PFX + "index", JSON.stringify(idx));
    ldel(PFX + "d." + id);
    var mapped = mirror.map[id];
    delete mirror.map[id]; saveMap();
    if (FS && mapped) {
      FS.deleteFile({ path: mapped, directory: lget(APP + "mirrorDir") || "DOCUMENTS" }).catch(function () {});
    }
    flushVault().then(function () { toast("已移入私密库，并删除了对应的 .md 文件"); });
  }
  function injectPiwiki() {
    var out = $("#pub-out");
    if (!out) return;
    var ready = !!PIWIKI.repo;
    out.parentNode.insertBefore(el('<div><div class="sub">发布到 PIWIKI</div>' +
      '<button class="pbtn soon block" type="button" id="app-piwiki" disabled><span>推送到 piwiki<br><small>' +
      (ready ? esc(PIWIKI.repo) : "未配置 · piwiki 仓库尚未建立") + '</small></span><span class="badge">SOON</span></button>' +
      '<p class="note">预留目标：等 piwiki 仓库建好后，在 <code>mobile/web/native.js</code> 的 <code>PIWIKI</code> 里填仓库名再启用。</p></div>'),
    out.nextSibling);
  }
  function injectHelp() {
    var help = $("#sheet-help .sheet-b");
    if (!help) return;
    var title = $("#sh-help-t");
    if (title) title.textContent = "使用说明";
    var web = $("ol", help);
    var ol = el("<ol>" +
      "<li><b>稿件就是 .md 文件</b><p>普通稿件随写随存，同时同步到 <code>Documents/pilog/posts/分类/文件名.md</code>，带 pilog 的 front matter。在「信息」里改分类或文件名就是重命名；在「稿件」里删除会一并删掉文件。</p></li>" +
      "<li><b>打开已有文件</b><p>「稿件 → 导入 .md」选择手机里的文件；「编辑线上文章」从 <code>pilog</code> 分支载入已发布的文章。</p></li>" +
      "<li><b>私密库</b><p>「稿件 → 进入私密库」，第一次设置密码。内容只以加密形式存在 App 私有目录，不生成 .md 文件；右上角锁形按钮立即上锁，离开 App 1 分钟也会自动上锁。解锁后可开启指纹解锁、修改密码，或把普通稿件移入。</p></li>" +
      "<li><b>开 PR 到 pilog</b><p>「稿件 → GitHub 令牌」粘贴只授权 <code>Meredith2328/pilog</code> 的 fine-grained token（Contents 与 Pull requests 读写），令牌由 Android Keystore 加密保存。之后「导出 → 发布（开 PR）」会新建 <code>write/日期-文件名</code> 分支并开 PR 到 <code>pilog</code>，在 GitHub 上审阅后手动合并。</p></li>" +
      "<li><b>导出与电脑同步</b><p>「导出 → 分享 / 导出 .md」走系统分享。USB 连电脑，把 <code>Documents/pilog/posts/</code> 拷进仓库的 <code>blogs/posts/</code> 即可。</p></li>" +
      "</ol>");
    if (web) web.replaceWith(ol); else help.insertBefore(ol, help.firstChild);
  }
  function call(name, arg) {
    if (!Sec || typeof Sec[name] !== "function") return Promise.resolve();
    try { return Promise.resolve(Sec[name](arg)).catch(function () {}); } catch (e) { return Promise.resolve(); }
  }
  function markReady() {
    requestAnimationFrame(function () { requestAnimationFrame(function () { call("ready"); }); });
  }
  function syncTheme() {
    var root = document.documentElement, last = null;
    function push() {
      var dark = root.dataset.theme === "dark";
      if (dark !== last) { last = dark; window.__pilogTheme = dark; call("setTheme", { dark: dark }); }
    }
    push();
    new MutationObserver(push).observe(root, { attributes: true, attributeFilter: ["data-theme"] });
  }

  /* ================= native export + links ================= */
  function nativeShare() {
    var w = api(), d = w.current(), name = (w.pathOf(d).split("/").pop()) || "note.md";
    var path = "export/" + name;
    FS.writeFile({ path: path, data: w.build(), directory: "CACHE", encoding: "utf8", recursive: true })
      .then(function () { return FS.getUri({ path: path, directory: "CACHE" }); })
      .then(function (r) { return Share.share({ title: d.title || name, files: [r.uri], dialogTitle: "导出 " + name }); })
      .then(function () { w.markExported(); }, function (e) {
        if (e && /cancel/i.test(e.message || "")) return;
        toast("导出失败：" + (e && e.message || e));
      });
  }
  window.addEventListener("click", function (e) {
    var t = e.target;
    if (isNative && t.closest && t.closest("#btn-download")) {
      e.preventDefault(); e.stopImmediatePropagation(); nativeShare(); return;
    }
    var a = t.closest && t.closest("a[href]");
    if (!a || !isNative) return;
    if (a.id === "brand") { e.preventDefault(); return; }
    var href = a.getAttribute("href");
    if (/^https?:\/\//i.test(href) && !/^https?:\/\/localhost\b/i.test(href)) {
      e.preventDefault(); e.stopImmediatePropagation();
      location.href = href;
    }
  }, true);

  /* ================= lifecycle ================= */
  document.addEventListener("visibilitychange", function () {
    if (space !== "vault" || !vaultMem) return;
    if (document.hidden) { vault.hiddenAt = Date.now(); flushVault(); }
    else if (vault.hiddenAt && Date.now() - vault.hiddenAt > AUTOLOCK_MS) lockVault();
  });
  window.addEventListener("pagehide", function () { if (vaultMem) flushVault(); });

  function boot() {
    /* the token is only read lazily by the publish UI, so a slow Keystore must not hold up the editor */
    var pre = Promise.race([loadToken(), new Promise(function (r) { setTimeout(r, 1500); })]);
    syncTheme();
    var ready = space === "vault" ? pre.then(gate) : pre;
    ready.then(function () {
      window.__pilogMain();
      if (space === "vault") injectVaultUi(); else { injectNotesUi(); reconcileMirror(); }
      injectPiwiki();
      injectHelp();
      showMirrorDir();
      markReady();
    }).catch(function (e) {
      markReady();
      console.error(e);
      toast("启动失败：" + (e && e.message || e));
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
