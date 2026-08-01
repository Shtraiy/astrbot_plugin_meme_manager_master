window.MemeManagerUI = window.MemeManagerUI || {};
window.MemeManagerUI.api = window.MemeManagerUI.api || {};
window.MemeManagerUI.api.withCurrentPageParams = function (pageName, extraParams = {}) {
    const allowedPages = new Set(["a_manage", "catalog", "settings", "semantic"]);
    if (!allowedPages.has(pageName)) {
      return null;
    }
    const currentParams = new URLSearchParams(window.location.search);
    for (const [key, value] of Object.entries(extraParams)) {
      if (value === null || value === undefined || value === "") {
        currentParams.delete(key);
      } else {
        currentParams.set(key, String(value));
      }
    }
    const routeParams = new URLSearchParams();
    for (const key of ["view", "managed_pack_id"]) {
      const value = currentParams.get(key);
      if (value) {
        routeParams.set(key, value);
      }
    }
    const nextUrl = new URL(window.location.origin + "/");
    const suffix = routeParams.toString() ? `?${routeParams}` : "";
    nextUrl.hash = `/plugin-page/meme_manager_master/${pageName}${suffix}`;
    return nextUrl;
  }
window.MemeManagerUI.api.applySecureNavLinks = function () {
    document.querySelectorAll("a[data-nav-page]").forEach((link) => {
      const pageName = link.getAttribute("data-nav-page");
      if (!pageName) {
        return;
      }
      const navView = link.getAttribute("data-nav-view") || "";
      const nextUrl = window.MemeManagerUI.api.withCurrentPageParams(pageName, {
        view: navView || null,
      });
      if (nextUrl) {
        link.target = "_top";
        link.href = nextUrl.toString();
      }
    });
  }
window.MemeManagerUI.api.apiGet = async function (endpoint, params = {}) {
    const mergedParams = { ...params };
    const managedPackId = String(
      window.MemeManagerUI.state.activeManagePackId ||
        window.MemeManagerUI.state.managePackSelect?.value ||
        window.MemeManagerUI.state.managedPackIdFromUrl ||
        "",
    ).trim();
    if (
      managedPackId &&
      [
        "emoji",
        "emotions",
        "meme_image",
        "meme_image_data",
      ].includes(endpoint)
    ) {
      mergedParams.managed_pack_id = managedPackId;
    }
    return await window.AstrBotPluginPage.apiGet(endpoint, mergedParams);
  }
window.MemeManagerUI.api.apiPost = async function (endpoint, body = {}) {
    const mergedBody = { ...body };
    const selectedPackId = String(
      window.MemeManagerUI.state.activeManagePackId ||
        window.MemeManagerUI.state.managePackSelect?.value ||
        window.MemeManagerUI.state.managedPackIdFromUrl ||
        "",
    ).trim();
    if (
      selectedPackId &&
      window.MemeManagerUI.state.defaultManagePackId &&
      selectedPackId !== window.MemeManagerUI.state.defaultManagePackId &&
      ["emoji/", "category/"].some((prefix) => endpoint.startsWith(prefix))
    ) {
      throw new Error(
        "当前为管理视图模式，仅支持浏览。请切回默认管理包后再执行编辑操作。",
      );
    }
    return await window.AstrBotPluginPage.apiPost(endpoint, mergedBody);
  }
window.MemeManagerUI.api.parseResponsePayload = async function (response) {
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      return response.json();
    }

    const text = await response.text();
    return {
      message:
        text.startsWith("<!DOCTYPE") || text.startsWith("<html")
          ? "服务器返回了错误页面，请联系管理员"
          : text,
    };
  }
window.MemeManagerUI.api.requestJson = async function (
    url,
    options = {},
    { defaultErrorMessage = "请求失败" } = {},
  ) {
    const response = await fetch(url, options);
    const payload = await window.MemeManagerUI.api.parseResponsePayload(response).catch(() => ({}));

    if (!response.ok) {
      const error = new Error(
        payload.message || payload.error || defaultErrorMessage,
      );
      error.status = response.status;
      error.code = payload.code || null;
      error.payload = payload;
      throw error;
    }

    return payload;
  }
window.MemeManagerUI.api.sleep = function (ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
