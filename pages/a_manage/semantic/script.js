async function initCaptureIndexPage() {
  const pageApi = window.AstrBotPluginPage;
  const packSelect = document.querySelector("#pack");
  const notice = document.querySelector("#notice");
  const summary = document.querySelector("#capture-summary");
  const folders = document.querySelector("#capture-folders");
  const indexedItems = document.querySelector("#capture-indexed-items");
  const pendingItems = document.querySelector("#capture-pending-items");
  const indexedCount = document.querySelector("#capture-indexed-count");
  const pendingCount = document.querySelector("#capture-pending-count");
  const refreshButton = document.querySelector("#capture-refresh-button");
  const indexButton = document.querySelector("#capture-index-button");
  const previewMask = document.querySelector("#preview-mask");
  const previewImage = document.querySelector("#preview-image");

  if (!pageApi) {
    notice.textContent = "请从 AstrBot WebUI 的插件页面打开表情索引。";
    return;
  }

  await pageApi.ready();
  document.querySelectorAll("a[data-nav-page]").forEach((link) => {
    link.removeAttribute("target");
  });

  const apiGet = (path, params = {}) => pageApi.apiGet(path, params);
  const apiPost = (path, body = {}) => pageApi.apiPost(path, body);
  const showError = (error) => {
    notice.textContent = String(error?.message || error || "操作失败");
    notice.classList.add("error");
  };

  function renderEmpty(target, message) {
    target.replaceChildren();
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = message;
    target.append(empty);
  }

  async function showPreview(item) {
    const relative = String(item.relative_path || "").split("/");
    const filename = relative.pop() || "";
    const category = relative[relative.length - 1] || "";
    if (!category || !filename || !packSelect.value) return;
    try {
      const data = await apiGet("meme_image_data", {
        managed_pack_id: packSelect.value,
        category,
        filename,
        size: "original",
      });
      previewImage.src = data.data_url || "";
      previewMask.classList.remove("hidden");
      previewMask.setAttribute("aria-hidden", "false");
    } catch (error) {
      showError(error);
    }
  }

  function renderCard(item, target) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `card${item.duplicate ? " duplicate" : ""}`;
    card.addEventListener("click", () => void showPreview(item));
    const title = document.createElement("strong");
    title.textContent = item.filename || "未命名图片";
    const meta = document.createElement("span");
    meta.textContent = `${item.category || "未分类"} · ${
      item.duplicate ? "重复待去重" : item.indexed ? "已索引" : "待分类"
    }`;
    const description = document.createElement("small");
    description.textContent = item.description || "点击查看图片";
    card.append(title, meta, description);
    target.append(card);
  }

  function renderWorkspace(data) {
    const stats = data.summary || {};
    summary.replaceChildren();
    for (const [label, value] of [
      ["已索引", stats.indexed || 0],
      ["待分类", stats.pending || 0],
      ["重复", stats.duplicate || 0],
      ["完成目录", `${stats.complete_folders || 0}/${stats.folder_total || 0}`],
    ]) {
      const item = document.createElement("div");
      item.className = "stat panel";
      item.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
      summary.append(item);
    }

    folders.replaceChildren();
    for (const folder of data.folders || []) {
      const chip = document.createElement("span");
      chip.className = `folder-chip${folder.complete ? " complete" : ""}`;
      chip.textContent = `${folder.category} · ${folder.indexed}/${folder.total}`;
      folders.append(chip);
    }

    indexedItems.replaceChildren();
    pendingItems.replaceChildren();
    const indexed = data.indexed_items || [];
    const pending = data.pending_items || [];
    indexedCount.textContent = `${stats.indexed || 0} 张`;
    pendingCount.textContent = `${(stats.pending || 0) + (stats.duplicate || 0)} 条`;
    if (indexed.length) indexed.forEach((item) => renderCard(item, indexedItems));
    else renderEmpty(indexedItems, "暂无已完成的偷取索引");
    if (pending.length) pending.forEach((item) => renderCard(item, pendingItems));
    else renderEmpty(pendingItems, "当前没有待处理偷取图片");

    const state = data.library_index || {};
    indexButton.disabled =
      state.status === "running" || !state.active_pack || !(stats.pending || stats.duplicate);
    notice.textContent = state.message || "目录索引已加载";
    notice.classList.remove("error");
  }

  async function loadWorkspace() {
    if (!packSelect.value) return;
    try {
      renderWorkspace(await apiGet("capture/workspace", { pack_id: packSelect.value }));
    } catch (error) {
      showError(error);
    }
  }

  async function loadPacks() {
    const data = await apiGet("packs");
    packSelect.replaceChildren();
    for (const pack of data.packs || []) {
      const option = document.createElement("option");
      option.value = String(pack.id || "");
      option.textContent = `${pack.name || pack.id || "未命名资源包"} (${pack.id || "-"})`;
      packSelect.append(option);
    }
  }

  packSelect.addEventListener("change", () => void loadWorkspace());
  refreshButton.addEventListener("click", () => void loadWorkspace());
  indexButton.addEventListener("click", async () => {
    indexButton.disabled = true;
    try {
      const result = await apiPost("capture/index", { pack_id: packSelect.value });
      notice.textContent = result.message || "分类索引已开始";
      await loadWorkspace();
    } catch (error) {
      showError(error);
    }
  });
  document.querySelector("#preview-close").addEventListener("click", () => {
    previewMask.classList.add("hidden");
    previewMask.setAttribute("aria-hidden", "true");
    previewImage.removeAttribute("src");
  });
  previewMask.addEventListener("click", (event) => {
    if (event.target === previewMask) document.querySelector("#preview-close").click();
  });

  try {
    await loadPacks();
    await loadWorkspace();
  } catch (error) {
    showError(error);
  }
}

void initCaptureIndexPage();
