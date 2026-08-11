window.MemeManagerUI = window.MemeManagerUI || {};
window.MemeManagerUI.api = window.MemeManagerUI.api || {};

window.MemeManagerUI.api.getSelectedPackId = function () {
  return String(
    window.MemeManagerUI.state.activeManagePackId ||
      window.MemeManagerUI.state.managePackSelect?.value ||
      window.MemeManagerUI.state.managedPackIdFromUrl ||
      "",
  ).trim();
};

window.MemeManagerUI.api.apiGet = async function (endpoint, params = {}) {
  const mergedParams = { ...params };
  const managedPackId = window.MemeManagerUI.api.getSelectedPackId();
  if (
    managedPackId &&
    ["emoji", "emotions", "meme_image", "meme_image_data", "sync/status"].includes(
      endpoint,
    )
  ) {
    mergedParams.managed_pack_id = managedPackId;
  }
  return await window.AstrBotPluginPage.apiGet(endpoint, mergedParams);
};

window.MemeManagerUI.api.apiPost = async function (endpoint, body = {}) {
  const mergedBody = { ...body };
  const managedPackId = window.MemeManagerUI.api.getSelectedPackId();
  if (
    managedPackId &&
    ["emoji/", "category/", "sync/"].some((prefix) => endpoint.startsWith(prefix))
  ) {
    mergedBody.managed_pack_id = managedPackId;
  }
  return await window.AstrBotPluginPage.apiPost(endpoint, mergedBody);
};

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
};

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
};

window.MemeManagerUI.api.sleep = function (ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
};
