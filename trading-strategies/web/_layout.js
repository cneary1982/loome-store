/* Shared sidebar + topbar + page-frame for every Loomi page.
   Each page calls renderLayout({active: "Dashboard"}) once on load,
   then renders its own content into <main id="main">. */

const TABS = [
  { name: "Dashboard",  icon: "dashboard",            href: "dashboard.html" },
  { name: "Strategies", icon: "auto_awesome",         href: "strategies.html" },
  { name: "Signals",    icon: "sensors",              href: "signals.html" },
  { name: "Backtest",   icon: "science",              href: "backtest.html" },
  { name: "Portfolio",  icon: "account_balance_wallet", href: "portfolio.html" },
  { name: "Analytics",  icon: "query_stats",          href: "analytics.html" },
  { name: "Terminal",   icon: "terminal",             href: "terminal.html" },
  { name: "Settings",   icon: "settings",             href: "settings.html" },
];

window.renderLayout = function ({ active = "Dashboard", title = "" } = {}) {
  const navHtml = TABS.map(t => {
    const isActive = t.name === active;
    return `
      <a href="${t.href}"
         class="flex items-center gap-sm px-sm py-base ${
           isActive
             ? "bg-primary text-on-primary rounded-lg font-bold"
             : "text-on-surface-variant hover:text-on-surface hover:bg-secondary-container rounded-lg"
         } transition-colors duration-150">
        <span class="material-symbols-outlined">${t.icon}</span>
        <span class="font-label-md text-label-md">${t.name}</span>
      </a>`;
  }).join("");

  const html = `
    <aside class="h-screen w-64 fixed left-0 top-0 flex flex-col bg-surface-container-lowest border-r border-outline-variant py-md px-sm z-50">
      <div class="mb-lg px-xs">
        <h1 class="font-headline-md text-headline-md font-bold text-primary tracking-tighter">Loomi.AI</h1>
        <p class="font-label-sm text-label-sm text-on-surface-variant opacity-70 uppercase tracking-widest mt-xs">Alpine Workspace</p>
      </div>
      <nav class="flex-1 space-y-1">${navHtml}</nav>
      <div class="mt-auto pt-md border-t border-outline-variant">
        <button id="killswitchSidebar"
          class="w-full py-sm bg-error/10 border border-error/30 text-error rounded-lg font-label-md text-label-md font-bold hover:bg-error hover:text-on-error transition-all flex items-center justify-center gap-xs">
          <span class="material-symbols-outlined">emergency_home</span>
          Kill Switch
        </button>
      </div>
    </aside>

    <header class="flex justify-between items-center h-16 w-full px-md ml-64 max-w-[calc(100%-16rem)]
                   border-b border-outline-variant bg-surface sticky top-0 z-40">
      <div class="flex items-center gap-md">
        <h2 class="font-headline-md text-headline-md font-bold text-primary">${title || active}</h2>
        <div id="liveBadge" class="flex items-center gap-sm bg-surface-container-low px-md py-xs rounded-full border border-outline-variant/30">
          <span class="w-2 h-2 rounded-full bg-on-tertiary-container animate-pulse"></span>
          <span class="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-tighter">Connecting…</span>
        </div>
      </div>
      <div class="flex items-center gap-md">
        <span id="halt-banner" class="hidden bg-error text-on-error px-md py-xs rounded font-label-sm font-bold">HALTED</span>
        <span id="env-badge" class="px-md py-xs rounded font-label-sm font-bold bg-surface-container-high text-on-surface-variant">--</span>
      </div>
    </header>
  `;

  document.body.insertAdjacentHTML("afterbegin", html);
  document.getElementById("killswitchSidebar").onclick = async () => {
    if (!confirm("HALT ALL TRADING? This cancels every open order.")) return;
    await fetch("/api/killswitch", { method: "POST" });
    alert("Kill switch engaged.");
    location.reload();
  };

  // Top-bar status poller
  async function pollStatus() {
    try {
      const r = await fetch("/api/state");
      const s = await r.json();
      document.getElementById("env-badge").textContent = s.broker_env || "—";
      document.getElementById("env-badge").className =
        "px-md py-xs rounded font-label-sm font-bold " +
        (s.broker_env === "sandbox"
          ? "bg-tertiary-fixed text-on-tertiary-fixed"
          : "bg-error text-on-error");
      document.getElementById("halt-banner").classList.toggle("hidden", !s.halted);
      const badge = document.getElementById("liveBadge");
      badge.innerHTML = `<span class="w-2 h-2 rounded-full ${
        s.halted ? "bg-error" : "bg-on-tertiary-container"
      } animate-pulse"></span>
      <span class="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-tighter">${
        s.halted ? "Halted" : "Live"
      }</span>`;
    } catch (e) {
      console.warn("status poll failed", e);
    }
  }
  pollStatus();
  setInterval(pollStatus, 5000);
};

window.fmt = {
  money: x => {
    if (x === null || x === undefined || isNaN(+x)) return "—";
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(+x);
  },
  pct: x => (x === null || x === undefined || isNaN(+x) ? "—" : (+x).toFixed(1) + "%"),
  num: (x, d = 2) => (x === null || x === undefined || isNaN(+x) ? "—" : (+x).toFixed(d)),
  signed: (x, d = 2) => {
    if (x === null || x === undefined || isNaN(+x)) return "—";
    const v = +x;
    return (v >= 0 ? "+" : "") + v.toFixed(d);
  },
  time: x => (x && x.includes("T") ? x.split("T")[1].slice(0, 8) : x || "—"),
};
