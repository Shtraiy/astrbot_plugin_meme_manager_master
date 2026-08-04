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
  const progressRow = document.querySelector(".capture-progress-row");
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
  let indexing = false;
  let indexPollTimer = null;

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

  function stopIndexPolling() {
    if (indexPollTimer !== null) {
      window.clearTimeout(indexPollTimer);
      indexPollTimer = null;
    }
  }

  function renderReindexProgress(state) {
    const status = String(state?.status || "idle");
    if (status === "idle" && !reindexing) {
      reindexProgress.hidden = true;
      progressRow.classList.remove("active");
      return;
    }
    const total = Math.max(Number(state?.total || 0), 1);
    const processed = Math.min(Math.max(Number(state?.processed || 0), 0), total);
    reindexProgress.hidden = false;
    progressRow.classList.add("active");
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
        reindexButton.setAttribute("aria-busy", "true");
        reindexPollTimer = window.setTimeout(() => void pollReindexStatus(), 500);
        return;
      }
      if (state.status === "error") {
        reindexing = false;
        reindexButton.disabled = false;
        reindexButton.setAttribute("aria-busy", "false");
        showError(new Error(state.message || "重索引失败"));
        return;
      }
      if (state.status === "completed") {
        reindexing = false;
        reindexButton.disabled = false;
        reindexButton.setAttribute("aria-busy", "false");
        const refreshed = await loadWorkspace();
        if (refreshed) {
          notice.textContent = state.message || "重索引已完成";
          notice.classList.remove("error");
        }
        return;
      }
      reindexing = false;
      reindexButton.disabled = false;
      reindexButton.setAttribute("aria-busy", "false");
    } catch (error) {
      reindexing = false;
      reindexButton.disabled = false;
      reindexButton.setAttribute("aria-busy", "false");
      showError(error);
    }
  }

  async function pollIndexStatus() {
    if (!packSelect.value || !indexing) return;
    try {
      const data = await loadWorkspace({ renderItems: false });
      const state = data?.library_index || {};
      const stillRunning = ["queued", "running"].includes(state.status)
        || (state.status === "idle" && state.message !== "没有待索引图片");
      if (indexing && stillRunning) {
        indexPollTimer = window.setTimeout(() => void pollIndexStatus(), 500);
        return;
      }
      indexing = false;
      indexPollTimer = null;
      if (data) renderWorkspace(data);
    } catch (error) {
      indexing = false;
      indexPollTimer = null;
      indexButton.disabled = false;
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
    const category = item.tag || item.category || "其他";
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

  async function deleteIndexedItem(item, card, button) {
    const location = getImageLocation(item);
    if (!location) return;
    if (!window.confirm(`确认永久删除 ${location.filename}？此操作不可恢复。`)) return;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    try {
      await apiPost("emoji/delete", {
        managed_pack_id: location.managed_pack_id,
        category: location.category,
        image_file: location.filename,
      });
      const refreshed = await loadWorkspace();
      if (refreshed) {
        notice.textContent = `已删除 ${location.filename}`;
        notice.classList.remove("error");
      } else {
        button.disabled = false;
        button.setAttribute("aria-busy", "false");
      }
    } catch (error) {
      button.disabled = false;
      button.setAttribute("aria-busy", "false");
      showError(error);
    }
  }

  function renderCard(item, target) {
    const card = document.createElement("article");
    card.className = `card thumbnail-loading${item.duplicate ? " duplicate" : ""}`;
    card.title = item.filename || "未命名图片";
    const previewButton = document.createElement("button");
    previewButton.type = "button";
    previewButton.className = "card-preview";
    previewButton.setAttribute("aria-label", `预览 ${item.filename || "图片"}`);
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
    previewButton.append(thumbnail, title, meta, description);
    const actions = document.createElement("div");
    actions.className = "card-actions";
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "card-delete";
    deleteButton.innerHTML = `
      <svg class="card-delete-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M9 3h6l1 2h4v2H4V5h4l1-2Zm-3 6h12l-.7 10.4A2.8 2.8 0 0 1 14.5 22h-5a2.8 2.8 0 0 1-2.8-2.6L6 9Zm3 2v7h2v-7H9Zm4 0v7h2v-7h-2Z" />
      </svg>`;
    deleteButton.setAttribute("aria-label", `永久删除 ${item.filename || "图片"}`);
    deleteButton.title = "永久删除图片";
    deleteButton.addEventListener("click", (event) => {
      event.stopPropagation();
      void deleteIndexedItem(item, card, deleteButton);
    });
    actions.append(deleteButton);
    card.append(previewButton, actions);
    target.append(card);
    card.addEventListener("click", (event) => {
      if (event.target !== card) return;
      if (card.classList.contains("thumbnail-error")) {
        void loadThumbnail(item, image, card);
      } else {
        void showPreview(item);
      }
    });
    previewButton.addEventListener("click", () => {
      if (card.classList.contains("thumbnail-error")) {
        void loadThumbnail(item, image, card);
        return;
      }
      void showPreview(item);
    });
    void loadThumbnail(item, image, card);
  }

  function renderWorkspace(data, { renderItems = true } = {}) {
    const stats = data.summary || {};
    summary.replaceChildren();
    for (const [label, value] of [
      ["已索引", stats.indexed || 0],
      ["待分类", stats.pending || 0],
      ["重复", stats.duplicate || 0],
      ["完成标签", `${stats.complete_folders || 0}/${stats.folder_total || 0}`],
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
    allCategories.textContent = "全部标签";
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

    const indexed = data.indexed_items || [];
    const pending = data.pending_items || [];
    indexedCount.textContent = `${stats.indexed || 0} 张`;
    pendingCount.textContent = `${(stats.pending || 0) + (stats.duplicate || 0)} 条`;
    if (renderItems) {
      indexedItems.replaceChildren();
      pendingItems.replaceChildren();
      if (indexed.length) indexed.forEach((item) => renderCard(item, indexedItems));
      else renderEmpty(indexedItems, "暂无已完成的偷取索引");
      if (pending.length) pending.forEach((item) => renderCard(item, pendingItems));
      else renderEmpty(pendingItems, "当前没有待处理偷取图片");
    }

    const state = data.library_index || {};
    const indexInProgress = indexing || ["queued", "running"].includes(state.status);
    indexButton.disabled =
      indexInProgress || !state.active_pack || !(stats.pending || stats.duplicate);
    indexButton.textContent = indexInProgress ? "分类索引中……" : "分类索引待处理项";
    reindexButton.disabled = reindexing;
    notice.textContent = indexing && state.status === "idle"
      ? "已提交分类索引，正在启动……"
      : state.message || "目录索引已加载";
    notice.classList.remove("error");
  }

  async function loadWorkspace({ renderItems = true } = {}) {
    if (!packSelect.value) return;
    try {
      const params = { pack_id: packSelect.value };
      if (selectedCategory) params.category = selectedCategory;
      const data = await apiGet("capture/workspace", params);
      renderWorkspace(data, { renderItems });
      return data;
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
    stopIndexPolling();
    selectedCategory = "";
    reindexing = false;
    indexing = false;
    reindexButton.setAttribute("aria-busy", "false");
    reindexProgress.hidden = true;
    progressRow.classList.remove("active");
    void loadWorkspace();
  });
  refreshButton.addEventListener("click", () => void loadWorkspace());
  indexButton.addEventListener("click", async () => {
    if (indexing || !packSelect.value) return;
    indexing = true;
    indexButton.disabled = true;
    try {
      const result = await apiPost("capture/index", { pack_id: packSelect.value });
      notice.textContent = result.message || "分类索引已开始";
      await loadWorkspace();
      void pollIndexStatus();
    } catch (error) {
      indexing = false;
      await loadWorkspace();
      showError(error);
    }
  });
  reindexButton.addEventListener("click", async () => {
    if (!packSelect.value || !window.confirm("将旧分类目录迁移到平铺目录，并按 meme_<哈希> 重建标签索引。继续吗？")) return;
    reindexing = true;
    reindexButton.disabled = true;
    reindexButton.setAttribute("aria-busy", "true");
    notice.classList.remove("error");
    notice.textContent = "正在重索引表情文件，请稍候……";
    try {
      const result = await apiPost("capture/reindex", { pack_id: packSelect.value });
      renderReindexProgress(result);
      void pollReindexStatus();
    } catch (error) {
      reindexing = false;
      reindexButton.disabled = false;
      reindexButton.setAttribute("aria-busy", "false");
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
    const initialWorkspace = await loadWorkspace();
    if (["queued", "running"].includes(initialWorkspace?.library_index?.status)) {
      indexing = true;
      void pollIndexStatus();
    }
    void pollReindexStatus();
  } catch (error) {
    showError(error);
  }
}

void initCaptureIndexPage();
