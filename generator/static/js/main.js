/* pilog — view switching, file tree, tag filter, dino widget */
(function () {
  "use strict";

  var VIEWS = ["cards", "tree", "graph"];

  function activateView(name, updateHash) {
    if (VIEWS.indexOf(name) < 0) return;
    document.querySelectorAll(".view-tab").forEach(function (tab) {
      var active = tab.dataset.view === name;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    document.querySelectorAll(".view-pane").forEach(function (pane) {
      pane.hidden = pane.dataset.pane !== name;
      pane.classList.toggle("is-active", pane.dataset.pane === name);
    });
    if (updateHash && history.replaceState) {
      history.replaceState(null, "", "#view-" + name);
    }
    if (name === "graph" && window.pilogGraph && !window.pilogGraph.started) {
      window.pilogGraph.start();
    }
  }

  document.querySelectorAll(".view-tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      activateView(tab.dataset.view, false);
    });
  });

  // deep links like #view-tree are honored explicitly; any other arrival
  // at the homepage defaults to the cards view
  var initial = null;
  if (location.hash.indexOf("#view-") === 0) {
    initial = location.hash.slice(6);
  }
  activateView(initial || "cards", false);

  // deep links reached via same-page hash changes (e.g. clicking a nav
  // folder link while already on the homepage)
  window.addEventListener("hashchange", function () {
    if (location.hash.indexOf("#view-") === 0) {
      activateView(location.hash.slice(6), false);
    }
  });

  /* ---------- file tree ---------- */
  var treeRoot = document.getElementById("tree-root");
  if (treeRoot) {
    treeRoot.querySelectorAll(".tree-folder > .tree-row").forEach(function (row) {
      row.addEventListener("click", function () {
        row.parentElement.classList.toggle("is-open");
      });
      row.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          row.parentElement.classList.toggle("is-open");
        }
      });
    });

    function setAll(open) {
      treeRoot.querySelectorAll(".tree-folder").forEach(function (li) {
        li.classList.toggle("is-open", open);
      });
    }

    var expandBtn = document.getElementById("tree-expand");
    var collapseBtn = document.getElementById("tree-collapse");
    if (expandBtn) expandBtn.addEventListener("click", function () { setAll(true); });
    if (collapseBtn) collapseBtn.addEventListener("click", function () { setAll(false); });
  }

  /* ---------- tag filter ---------- */
  var filterBar = document.getElementById("tag-filter");
  var cardGrid = document.getElementById("card-grid");
  if (filterBar && cardGrid) {
    var cards = Array.prototype.slice.call(cardGrid.querySelectorAll(".card"));
    filterBar.addEventListener("click", function (e) {
      var chip = e.target.closest(".filter-chip");
      if (!chip) return;
      var tag = chip.dataset.tag;
      filterBar.querySelectorAll(".filter-chip").forEach(function (c) {
        c.classList.toggle("is-active", c === chip);
      });
      var empty = cardGrid.querySelector(".empty-cards");
      if (empty) empty.remove();
      var shown = 0;
      cards.forEach(function (card) {
        var tags = (card.dataset.tags || "").split(/\s+/).filter(Boolean);
        var match = tag === "*" || tags.indexOf(tag) >= 0;
        card.hidden = !match;
        if (match) shown++;
      });
      if (!shown) {
        var div = document.createElement("div");
        div.className = "empty-cards";
        div.textContent = "没有匹配「" + tag + "」的文章";
        cardGrid.appendChild(div);
      }
    });
  }

  /* ---------- dino widget ---------- */
  var widget = document.querySelector('[data-widget="dino"]');
  if (widget) {
    var toggle = widget.querySelector(".dino-toggle");
    var panel = widget.querySelector(".dino-panel");
    var close = widget.querySelector(".dino-close");
    var frame = widget.querySelector(".dino-frame");

    function open(force) {
      var show = force === undefined ? panel.hidden : !!force;
      panel.hidden = !show;
      toggle.classList.toggle("is-open", show);
      toggle.setAttribute("aria-label", show ? "关闭小恐龙游戏" : "打开小恐龙游戏");
      if (show && frame && frame.dataset.src) {
        frame.src = frame.dataset.src;
      }
    }

    toggle.addEventListener("click", function () { open(); });
    if (close) close.addEventListener("click", function () { open(false); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") open(false);
    });
    open(false);
  }
})();
