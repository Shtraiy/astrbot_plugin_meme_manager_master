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
  const reindexButton = document.querySelector("#capture-reindex-button");
  const reindexProgress = document.querySelector("#capture-reindex-progress");
  const reindexProgressLabel = document.querySelector("#capture-reindex-progress-label");
  const reindexProgressCount = document.querySelector("#capture-reindex-progress-count");
  const reindexProgressBar = document.querySelector("#capture-reindex-progress-bar");
  const indexButton = document.querySelector("#capture-index-button");
  const categoryFilters = document.querySelector("#capture-category-filters");
  const previewMask = document.querySelector("#preview-mask");
  const previewImage = document.querySelector("#preview-image");
  let selectedCategory = "";
  let reindexing = false;
  let reindexPollTimer = null;

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

  function stopReindexPolling() {
    if (reindexPollTimer !== null) {
      window.clearTimeout(reindexPollTimer);
      reindexPollTimer = null;
    }
  }

  function renderReindexProgress(state) {
    const status = String(state?.status || "idle");
    if (status === "idle" && !reindexing) {
      reindexProgress.hidden = true;
      return;
    }
    const total = Math.max(Number(state?.total || 0), 1);
    const processed = Math.min(Math.max(Number(state?.processed || 0), 0), total);
    reindexProgress.hidden = false;
    reindexProgress.classList.toggle("error", status === "error");
    reindexProgressLabel.textContent = String(state?.message || "正在准备重索引……");
    reindexProgressCount.textContent = `${processed}/${Number(state?.total || 0)}`;
    reindexProgressBar.max = total;
    reindexProgressBar.value = processed;
  }

  async function pollReindexStatus() {
    if (!packSelect.value) return;
    try {
      const state = await apiGet("capture/reindex/status", { pack_id: packSelect.value });
      renderReindexProgress(state);
      if (state.status === "running") {
        reindexing = true;
        reindexButton.disabled = true;
        reindexPollTimer = window.setTimeout(() => void pollReindexStatus(), 500);
        return;
      }
      reindexing = false;
      reindexButton.disabled = false;
      if (state.status !== "idle") await loadWorkspace();
    } catch (error) {
      reindexing = false;
      reindexButton.disabled = false;
      showError(error);
    }
  }

  function renderEmpty(target, message) {
    target.replaceChildren();
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = message;
    target.append(empty);
  }

  function getImageLocation(item) {
    const relative = String(item.relative_path || "").split("/");
    const filename = relative.pop() || "";
    const category = relative[relative.length - 1] || "";
    if (!category || !filename || !packSelect.value) return null;
    return { managed_pack_id: packSelect.value, category, filename };
  }

  async function showPreview(item) {
    const location = getImageLocation(item);
    if (!location) return;
    try {
      const data = await apiGet("meme_image_data", {
        ...location,
        size: "original",
      });
      previewImage.src = data.data_url || "";
      previewMask.classList.remove("hidden");
      previewMask.setAttribute("aria-hidden", "false");
    } catch (error) {
      showError(error);
    }
  }

  function markThumbnailError(image, card) {
    image.removeAttribute("src");
    card.classList.remove("thumbnail-loading", "thumbnail-loaded");
    card.classList.add("thumbnail-error");
  }

  async function loadThumbnail(item, image, card) {
    const location = getImageLocation(item);
    if (!location) return;
    card.classList.remove("thumbnail-error", "thumbnail-loaded");
    card.classList.add("thumbnail-loading");
    try {
      const data = await apiGet("meme_image_data", { ...location, size: "preview" });
      if (!data.data_url) throw new Error("缩略图数据为空");
      image.src = data.data_url;
      card.classList.remove("thumbnail-loading");
      card.classList.add("thumbnail-loaded");
    } catch (error) {
      markThumbnailError(image, card);
    }
  }

  function renderCard(item, target) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `card thumbnail-loading${item.duplicate ? " duplicate" : ""}`;
    card.title = item.filename || "未命名图片";
    const thumbnail = document.createElement("span");
    thumbnail.className = "card-thumbnail";
    thumbnail.setAttribute("aria-hidden", "true");
    const image = document.createElement("img");
    image.className = "thumbnail-image";
    image.loading = "lazy";
    image.alt = "";
    image.addEventListener("error", () => markThumbnailError(image, card));
    const placeholder = document.createElement("span");
    placeholder.className = "thumbnail-placeholder";
    placeholder.textContent = "加载缩略图";
    const errorText = document.createElement("span");
    errorText.className = "thumbnail-error-text";
    errorText.textContent = "缩略图加载失败，点击重试";
    thumbnail.append(image, placeholder, errorText);
    const title = document.createElement("strong");
    title.textContent = item.filename || "未命名图片";
    const meta = document.createElement("span");
    meta.textContent = `${item.category || "未分类"} · ${
      item.duplicate ? "重复待去重" : item.indexed ? "已索引" : "待分类"
    }`;
    const description = document.createElement("small");
    description.textContent = item.description || "点击查看图片";
    card.setAttribute("aria-label", `${title.textContent}，${meta.textContent}`);
    card.append(thumbnail, title, meta, description);
    target.append(card);
    card.addEventListener("click", () => {
      if (card.classList.contains("thumbnail-error")) {
        void loadThumbnail(item, image, card);
        return;
      }
      void showPreview(item);
    });
    void loadThumbnail(item, image, card);
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

    categoryFilters.replaceChildren();
    const allCategories = document.createElement("button");
    allCategories.type = "button";
    allCategories.className = `category-filter${selectedCategory ? "" : " active"}`;
    allCategories.textContent = "全部分类";
    allCategories.addEventListener("click", () => {
      selectedCategory = "";
      void loadWorkspace();
    });
    categoryFilters.append(allCategories);
    for (const folder of data.folders || []) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `category-filter${selectedCategory === folder.category ? " active" : ""}`;
      button.textContent = folder.category;
      button.addEventListener("click", () => {
        selectedCategory = folder.category;
        void loadWorkspace();
      });
      categoryFilters.append(button);
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
    reindexButton.disabled = reindexing;
    notice.textContent = state.message || "目录索引已加载";
    notice.classList.remove("error");
  }

  async function loadWorkspace() {
    if (!packSelect.value) return;
    try {
      const params = { pack_id: packSelect.value };
      if (selectedCategory) params.category = selectedCategory;
      renderWorkspace(await apiGet("capture/workspace", params));
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

  packSelect.addEventListener("change", () => {
    stopReindexPolling();
    selectedCategory = "";
    reindexing = false;
    reindexProgress.hidden = true;
    void loadWorkspace();
  });
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
  reindexButton.addEventListener("click", async () => {
    if (!packSelect.value || !window.confirm("只重新编号并同步索引中的文件名，不会重新识别表情。继续吗？")) return;
    reindexing = true;
    reindexButton.disabled = true;
    notice.classList.remove("error");
    notice.textContent = "正在重索引表情文件，请稍候……";
    try {
      const result = await apiPost("capture/reindex", { pack_id: packSelect.value });
      renderReindexProgress(result);
      void pollReindexStatus();
    } catch (error) {
      reindexing = false;
      reindexButton.disabled = false;
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
    void pollReindexStatus();
  } catch (error) {
    showError(error);
  }
}

void initCaptureIndexPage();
