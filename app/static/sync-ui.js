(function () {
  const SPINNER_LINES = [
    "Grabbing your Letterboxd watchlist…",
    "Looking up your films…",
    "Pulling Letterboxd ratings…",
    "Sorting into moods…",
  ];
  const ROTATE_MS = 2500;

  let rotateTimer = null;
  let lineIndex = 0;

  function getLoadingHtml() {
    const template = document.getElementById("results-loading-template");
    return template ? template.innerHTML : "";
  }

  function showSpinnerLine(index) {
    const spinner = document.getElementById("spinner");
    if (!spinner) return;
    const lines = spinner.querySelectorAll(".spinner-line");
    lines.forEach((line, i) => {
      line.hidden = i !== index;
    });
  }

  function startSpinnerRotation() {
    lineIndex = 0;
    showSpinnerLine(0);
    if (rotateTimer) clearInterval(rotateTimer);
    rotateTimer = setInterval(() => {
      lineIndex = (lineIndex + 1) % SPINNER_LINES.length;
      showSpinnerLine(lineIndex);
    }, ROTATE_MS);
  }

  function stopSpinnerRotation() {
    if (rotateTimer) {
      clearInterval(rotateTimer);
      rotateTimer = null;
    }
    showSpinnerLine(0);
  }

  document.body.addEventListener("htmx:beforeRequest", (event) => {
    const form = event.detail.elt;
    if (!form || !form.classList.contains("search-form")) return;
    const results = document.getElementById("results");
    if (results) {
      results.innerHTML = getLoadingHtml();
    }
    startSpinnerRotation();
  });

  document.body.addEventListener("htmx:afterRequest", (event) => {
    const form = event.detail.elt;
    if (!form || !form.classList.contains("search-form")) return;
    stopSpinnerRotation();
  });

  document.body.addEventListener("htmx:responseError", (event) => {
    const form = event.detail.elt;
    if (!form || !form.classList.contains("search-form")) return;
    stopSpinnerRotation();
  });
})();
