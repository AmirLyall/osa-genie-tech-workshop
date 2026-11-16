/* NC OSA Genie technical workshop site: settings, tabs, progress, copy buttons, clear, print, active nav. */
(function () {
  const store = {
    get: (k, d) => { try { return JSON.parse(localStorage.getItem("osa-genie-tech:" + k)) ?? d; } catch (e) { return d; } },
    set: (k, v) => localStorage.setItem("osa-genie-tech:" + k, JSON.stringify(v)),
  };
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));

  /* ---------- your settings: fill {{CATALOG}}, {{SANDBOX}}, {{NAME}} and {{AGENT}} in every snippet ---------- */
  const FIELDS = { CATALOG: "<catalog>", SCHEMA: "osa_pcard_review", SANDBOX: "<your_schema>", NAME: "<yourname>", AGENT: "<your agent URL: paste it in step 4 above>" };
  const settings = store.get("settings", {});
  // AGENT_ID is the 32-character ID inside the agent URL.
  const agentId = () => ((settings.AGENT || "").match(/[0-9a-f]{32}/) || [])[0] || "<your agent ID: paste the agent URL in section 2>";
  const fill = (text) => text.replace(/\{\{AGENT_ID\}\}/g, agentId)
    .replace(/\{\{(CATALOG|SCHEMA|SANDBOX|NAME|AGENT)\}\}/g, (m, k) => (settings[k] || "").trim() || FIELDS[k]);
  $$("[data-tpl]").forEach((el) => { el.dataset.template = el.textContent; });
  function render() { $$("[data-tpl]").forEach((el) => { el.textContent = fill(el.dataset.template); }); }
  $$(".settings-box input[data-setting]").forEach((input) => {
    const key = input.dataset.setting;
    input.value = settings[key] || "";
    input.addEventListener("input", () => {
      // names go into object names, so keep them to letters, digits and underscores
      settings[key] = key === "NAME" ? input.value.toLowerCase().replace(/[^a-z0-9_]/g, "") : input.value;
      store.set("settings", settings); render();
    });
  });
  render();

  /* ---------- copy buttons ---------- */
  function copyBtn(getText) {
    const b = document.createElement("button");
    b.className = "copy"; b.type = "button"; b.textContent = "Copy";
    b.addEventListener("click", async (e) => {
      e.preventDefault(); e.stopPropagation();
      try { await navigator.clipboard.writeText(getText()); } catch (err) {
        const t = document.createElement("textarea"); t.value = getText(); document.body.appendChild(t); t.select(); document.execCommand("copy"); t.remove();
      }
      b.textContent = "Copied"; b.classList.add("done");
      setTimeout(() => { b.textContent = "Copy"; b.classList.remove("done"); }, 1400);
    });
    return b;
  }
  // Copy reads the text at click time, so it picks up the settings above.
  $$("p.q").forEach((q) => { const span = $("[data-tpl]", q); const t = q.textContent.trim(); q.appendChild(copyBtn(() => (span ? span.textContent : t).trim())); });
  $$(".codeblock").forEach((box) => { const pre = $("pre", box); box.appendChild(copyBtn(() => pre.textContent)); });

  /* ---------- tabs ---------- */
  $$(".tabs").forEach((tabs) => {
    const bar = $(".tab-buttons", tabs);
    if (bar && tabs.dataset.label) { const l = document.createElement("span"); l.className = "tab-label"; l.textContent = tabs.dataset.label; bar.prepend(l); }
    const key = "tab:" + tabs.dataset.tabs;
    const show = (id) => {
      $$(".tab-buttons button", tabs).forEach((b) => b.classList.toggle("active", b.dataset.tab === id));
      $$(".tab-panel", tabs).forEach((p) => p.classList.toggle("active", p.id === id));
    };
    $$(".tab-buttons button", tabs).forEach((b) => b.addEventListener("click", () => { show(b.dataset.tab); store.set(key, b.dataset.tab); }));
    const saved = store.get(key, null);
    if (saved && $("#" + saved, tabs)) show(saved);
  });

  /* ---------- checklists + progress ---------- */
  const checks = store.get("checks", {});
  const boxes = $$('input[type="checkbox"][data-id]');
  function updateProgress() {
    const done = boxes.filter((b) => b.checked).length;
    const pct = boxes.length ? Math.round((100 * done) / boxes.length) : 0;
    $("#progress-bar").style.width = pct + "%"; $("#progress-label").textContent = pct + "%";
  }
  boxes.forEach((b) => {
    b.checked = !!checks[b.dataset.id];
    b.addEventListener("change", () => { checks[b.dataset.id] = b.checked; store.set("checks", checks); updateProgress(); });
  });
  updateProgress();

  /* ---------- clear progress ---------- */
  $("#reset-btn").addEventListener("click", () => {
    if (!confirm("Clear your checkmarks and settings and start the guide over?")) return;
    Object.keys(localStorage).filter((k) => k.startsWith("osa-genie-tech:")).forEach((k) => localStorage.removeItem(k));
    location.reload();
  });

  /* ---------- print ---------- */
  let closedForPrint = [];
  window.addEventListener("beforeprint", () => {
    $$(".tab-panel").forEach((p) => p.classList.add("print-show"));
    closedForPrint = $$("details:not([open])");
    closedForPrint.forEach((d) => d.setAttribute("open", ""));
  });
  window.addEventListener("afterprint", () => {
    $$(".tab-panel").forEach((p) => p.classList.remove("print-show"));
    closedForPrint.forEach((d) => d.removeAttribute("open")); closedForPrint = [];
  });
  $("#print-btn").addEventListener("click", () => window.print());

  /* ---------- active nav ---------- */
  const links = $$(".sidebar a");
  const sections = links.map((a) => document.querySelector(a.getAttribute("href"))).filter(Boolean);
  const obs = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (e.isIntersecting) links.forEach((a) => a.classList.toggle("active", a.getAttribute("href") === "#" + e.target.id));
    });
  }, { rootMargin: "-40% 0px -55% 0px" });
  sections.forEach((s) => obs.observe(s));
})();
