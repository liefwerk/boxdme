(function () {
  function getExplorer() {
    return document.querySelector(".mood-explorer");
  }

  function getStarHalfSteps(explorer) {
    const checked = explorer.querySelector('input[name="rating-filter"]:checked');
    if (!checked || !checked.id.startsWith("filter-hs-")) {
      return 0;
    }
    return parseInt(checked.id.replace("filter-hs-", ""), 10) || 0;
  }

  function rowMatchesStar(row, halfSteps) {
    if (halfSteps === 0) {
      return true;
    }
    return row.classList.contains(`hs-ge-${halfSteps}`);
  }

  function countMatchingRows(container, halfSteps) {
    let count = 0;
    container.querySelectorAll(".film-row").forEach((row) => {
      if (rowMatchesStar(row, halfSteps)) {
        count += 1;
      }
    });
    return count;
  }

  function isSubPanelShown(subPanel) {
    return window.getComputedStyle(subPanel).display !== "none";
  }

  function subSlugFromInputId(inputId, moodSlug) {
    const prefix = `sub-${moodSlug}-`;
    if (!inputId.startsWith(prefix)) {
      return null;
    }
    return inputId.slice(prefix.length);
  }

  function updatePanel(panel, halfSteps) {
    const moodSlug = panel.dataset.mood;
    if (!moodSlug) {
      return;
    }

    panel.querySelectorAll(".sub-mood-filter-bar label.rating-filter-chip").forEach((label) => {
      const forId = label.getAttribute("for");
      if (!forId) {
        return;
      }
      const countEl = label.querySelector(".vibe-count");
      if (!countEl) {
        return;
      }

      let count = 0;
      if (forId === `sub-${moodSlug}-all`) {
        count = countMatchingRows(panel, halfSteps);
      } else {
        const subSlug = subSlugFromInputId(forId, moodSlug);
        const subPanel = panel.querySelector(`.sub-mood-panel[data-sub-mood="${subSlug}"]`);
        if (subPanel) {
          count = countMatchingRows(subPanel, halfSteps);
        }
      }
      countEl.textContent = String(count);
    });

    let visible = 0;
    let scopeTotal = 0;
    panel.querySelectorAll(".sub-mood-panel").forEach((subPanel) => {
      if (!isSubPanelShown(subPanel)) {
        return;
      }
      visible += countMatchingRows(subPanel, halfSteps);
      scopeTotal += subPanel.querySelectorAll(".film-row").length;
    });

    const badge = panel.querySelector(".mood-selection-count");
    if (!badge) {
      return;
    }

    const filtered = halfSteps > 0 || visible !== scopeTotal;
    if (filtered) {
      badge.textContent = `${visible} of ${scopeTotal} shown`;
    } else {
      badge.textContent = `${scopeTotal} films`;
    }
  }

  function updateAllFilterCounts() {
    const explorer = getExplorer();
    if (!explorer) {
      return;
    }
    const halfSteps = getStarHalfSteps(explorer);
    explorer.querySelectorAll(".mood-detail-panel").forEach((panel) => {
      updatePanel(panel, halfSteps);
    });
  }

  document.body.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) {
      return;
    }
    if (
      target.name === "rating-filter" ||
      target.name === "mood-tab" ||
      (target.name && target.name.startsWith("sub-mood-"))
    ) {
      updateAllFilterCounts();
    }
  });

  document.body.addEventListener("htmx:afterSwap", (event) => {
    if (event.detail.target && event.detail.target.id === "results") {
      updateAllFilterCounts();
    }
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", updateAllFilterCounts);
  } else {
    updateAllFilterCounts();
  }
})();
