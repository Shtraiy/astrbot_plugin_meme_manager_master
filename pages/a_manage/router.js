window.MemeManagerUI = window.MemeManagerUI || {};

const routes = {
  manage: {
    initializer: "initManageView",
    activator: "activateManageView",
  },
  index: {
    initializer: "initCaptureIndexView",
    activator: "activateCaptureIndexView",
  },
  settings: {
    initializer: "initSettingsView",
    activator: "activateSettingsView",
  },
};

const initializedRoutes = new Set();
let routerStarted = false;

function currentRoute() {
  const requested = String(window.location.hash || "")
    .replace(/^#/, "")
    .trim()
    .toLowerCase();
  return Object.hasOwn(routes, requested) ? requested : "manage";
}

function replaceRoute(route) {
  const nextUrl = new URL(window.location.href);
  nextUrl.hash = `#${route}`;
  window.history.replaceState(window.history.state, "", nextUrl.toString());
}

async function renderRoute() {
  const route = currentRoute();
  if (window.location.hash !== `#${route}`) replaceRoute(route);

  document.querySelectorAll("[data-view]").forEach((view) => {
    view.hidden = view.dataset.view !== route;
  });
  document.querySelectorAll("[data-route]").forEach((link) => {
    const active = link.dataset.route === route;
    link.setAttribute("aria-current", active ? "page" : "false");
  });
  document.documentElement.dataset.currentView = route;

  const definition = routes[route];
  if (!initializedRoutes.has(route)) {
    const initializer = window.MemeManagerUI[definition.initializer];
    if (typeof initializer !== "function") {
      throw new Error(`缺少视图初始化函数：${definition.initializer}`);
    }
    initializedRoutes.add(route);
    try {
      await initializer();
    } catch (error) {
      initializedRoutes.delete(route);
      throw error;
    }
  }

  const activator = window.MemeManagerUI[definition.activator];
  if (typeof activator === "function") await activator();
}

async function start() {
  if (routerStarted) return;
  routerStarted = true;
  window.addEventListener("hashchange", renderRoute);
  await renderRoute();
}

function updateManagedPackQuery(packId) {
  const nextUrl = new URL(window.location.href);
  const normalized = String(packId || "").trim();
  if (normalized) nextUrl.searchParams.set("managed_pack_id", normalized);
  else nextUrl.searchParams.delete("managed_pack_id");
  window.history.replaceState(window.history.state, "", nextUrl.toString());
}

window.MemeManagerUI.router = {
  currentRoute,
  renderRoute,
  start,
  updateManagedPackQuery,
};

void start();
