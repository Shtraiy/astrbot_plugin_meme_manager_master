window.MemeManagerUI = window.MemeManagerUI || {};
window.MemeManagerUI.api = window.MemeManagerUI.api || {};
window.MemeManagerUI.api.withCurrentPageParams = function (targetPath, extraParams = {}) {
    const nextUrl = new URL(targetPath, window.location.href);
    const currentParams = new URLSearchParams(window.location.search);
    for (const key of ["view", "managed_pack_id"]) {
      const value = currentParams.get(key);
      if (value && !nextUrl.searchParams.has(key)) {
        nextUrl.searchParams.set(key, value);
      }
    }
    for (const [key, value] of Object.entries(extraParams)) {
      if (value === null || value === undefined || value === "") {
        nextUrl.searchParams.delete(key);
      } else {
        nextUrl.searchParams.set(key, String(value));
      }
    }
    return nextUrl;
  }
window.MemeManagerUI.api.applySecureNavLinks = function () {
    document.querySelectorAll("a[data-nav-target]").forEach((link) => {
      const targetPath = link.getAttribute("data-nav-target");
      if (!targetPath) {
        return;
      }
      const navView = link.getAttribute("data-nav-view") || "";
      const nextUrl = window.MemeManagerUI.api.withCurrentPageParams(targetPath, {
        view: navView || null,
      });
      link.href = nextUrl.toString();
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
        "meme_image_semantic",
        "semantic/reviews",
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
    if (selectedPackId && endpoint.startsWith("semantic/")) {
      mergedBody.pack_id = selectedPackId;
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
