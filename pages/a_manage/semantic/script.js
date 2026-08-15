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
  const selectionModeButton = document.querySelector("#capture-selection-mode-button");
  const selectIndexedPageButton = document.querySelector("#capture-select-indexed-page-button");
  const selectPendingButton = document.querySelector("#capture-select-pending-button");
  const clearSelectionButton = document.querySelector("#capture-clear-selection-button");
  const selectionSummary = document.querySelector("#capture-selection-summary");
  const indexedHeading = document.querySelector("#capture-indexed-heading");
  const categoryFilters = document.querySelector("#capture-category-filters");
  const pagination = document.querySelector("#capture-pagination");
  const paginationPrev = document.querySelector("#capture-pagination-prev");
  const paginationNext = document.querySelector("#capture-pagination-next");
  const paginationPages = document.querySelector("#capture-pagination-pages");
  const paginationSummary = document.querySelector("#capture-pagination-summary");
  const previewMask = document.querySelector("#preview-mask");
  const previewImage = document.querySelector("#preview-image");
  const confirmMask = document.querySelector("#capture-confirm-mask");
  const confirmTitle = document.querySelector("#capture-confirm-title");
  const confirmDescription = document.querySelector("#capture-confirm-description");
  const confirmCancel = document.querySelector("#capture-confirm-cancel");
  const confirmConfirm = document.querySelector("#capture-confirm-confirm");
  let selectedCategory = "";
  let reindexing = false;
  let reindexPollTimer = null;
  let reindexPollGeneration = 0;
  let indexing = false;
  let indexPollTimer = null;
  let pendingConfirmation = null;
  let currentWorkspace = null;
  let selectionMode = false;
  const selectedItems = new Map();
  const failedDisposals = new Map();
  let mutationInProgress = false;
  let disposalOperationGeneration = 0;
  let currentPage = 1;
  let workspaceRequestGeneration = 0;
  const THUMBNAIL_CACHE_MAX_ENTRIES = 512;
  const THUMBNAIL_CACHE_MAX_BYTES = 64 * 1024 * 1024;
  const thumbnailCache = new Map();
  const thumbnailRequests = new Map();
  let thumbnailCacheBytes = 0;

  if (!pageApi) {
    notice.textContent = "请从 AstrBot WebUI 的插件页面打开表情索引。";
    return;
  }

  await pageApi.ready();
  const allowedPages = new Set(["a_manage", "catalog", "settings", "semantic"]);
  const currentParams = new URLSearchParams(window.location?.search || "");
  document.querySelectorAll("a[data-nav-page]").forEach((link) => {
    const pageName = link.getAttribute("data-nav-page");
    if (!pageName || !allowedPages.has(pageName)) {
      return;
    }
    const nextUrl = new URL(link.href, window.location.href);
    const navView = link.getAttribute("data-nav-view") || "";
    if (navView) {
      nextUrl.searchParams.set("view", navView);
    } else {
      nextUrl.searchParams.delete("view");
    }
    const managedPackId = currentParams.get("managed_pack_id");
    if (managedPackId) {
      nextUrl.searchParams.set("managed_pack_id", managedPackId);
    } else {
      nextUrl.searchParams.delete("managed_pack_id");
    }
    link.removeAttribute("target");
    link.href = nextUrl.toString();
  });

  const apiGet = (path, params = {}) => pageApi.apiGet(path, params);
  const apiPost = (path, body = {}) => pageApi.apiPost(path, body);
  const showError = (error) => {
    notice.textContent = String(error?.message || error || "操作失败");
    notice.classList.add("error");
  };

  function closeConfirmation(result) {
    const resolver = pendingConfirmation;
    pendingConfirmation = null;
    confirmMask.classList.add("hidden");
    confirmMask.setAttribute("aria-hidden", "true");
    if (resolver) resolver(Boolean(result));
  }

  function requestConfirmation(description, title = "请确认操作") {
    return new Promise((resolve) => {
      pendingConfirmation = resolve;
      confirmTitle.textContent = title;
      confirmDescription.textContent = description;
      confirmMask.classList.remove("hidden");
      confirmMask.setAttribute("aria-hidden", "false");
      confirmConfirm.focus?.();
    });
  }

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
    reindexProgress.classList.toggle(
      "error",
      ["error", "completed_with_errors"].includes(status),
    );
    const skipped = Math.max(Number(state?.skipped || 0), 0);
    const reindexed = Math.max(Number(state?.reindexed || 0), 0);
    const errors = Math.max(Number(state?.errors || 0), 0);
    reindexProgressLabel.textContent = `${String(
      state?.message || "正在准备全量语义重索引……",
    )}（跳过 ${skipped} · 重识别 ${reindexed} · 失败 ${errors}）`;
    reindexProgressCount.textContent = `${processed}/${Number(state?.total || 0)}`;
    reindexProgressBar.max = total;
    reindexProgressBar.value = processed;
  }

  async function pollReindexStatus(generation = reindexPollGeneration) {
    const packId = packSelect.value;
    if (!packId) return;
    try {
      const state = await apiGet("capture/reindex/status", { pack_id: packId });
      if (generation !== reindexPollGeneration || packSelect.value !== packId) return;
      renderReindexProgress(state);
      if (state.status === "running") {
        reindexing = true;
        reindexButton.disabled = true;
        reindexButton.setAttribute("aria-busy", "true");
        reindexPollTimer = window.setTimeout(() => void pollReindexStatus(generation), 500);
        return;
      }
      if (state.status === "error") {
        reindexing = false;
        reindexButton.disabled = false;
        reindexButton.setAttribute("aria-busy", "false");
        showError(new Error(state.message || "重索引失败"));
        return;
      }
      if (["completed", "completed_with_errors"].includes(state.status)) {
        const shouldClearThumbnails = reindexing;
        reindexing = false;
        reindexButton.disabled = false;
        reindexButton.setAttribute("aria-busy", "false");
        if (shouldClearThumbnails) clearThumbnailCache();
        const refreshed = await loadWorkspace();
        if (generation !== reindexPollGeneration || packSelect.value !== packId) return;
        if (refreshed) {
          notice.textContent = state.message || "重索引已完成";
          notice.classList.toggle("error", state.status === "completed_with_errors");
        }
        return;
      }
      reindexing = false;
      reindexButton.disabled = false;
      reindexButton.setAttribute("aria-busy", "false");
    } catch (error) {
      if (generation !== reindexPollGeneration || packSelect.value !== packId) return;
      reindexing = false;
      reindexButton.disabled = false;
      reindexButton.setAttribute("aria-busy", "false");
      showError(error);
    }
  }

  async function pollIndexStatus() {
    if (!packSelect.value || !indexing) return;
    try {
      const state = await apiGet("capture/index/status", { pack_id: packSelect.value });
      if (["queued", "running"].includes(state.status)) {
        notice.textContent = state.message || "分类索引处理中……";
        notice.classList.remove("error");
        indexPollTimer = window.setTimeout(() => void pollIndexStatus(), 500);
        return;
      }
      indexing = false;
      indexPollTimer = null;
      if (state.status === "error") {
        indexButton.disabled = false;
        showError(new Error(state.message || "分类索引失败"));
        return;
      }
      const data = await loadWorkspace();
      if (data) {
        notice.textContent = state.message || "分类索引已完成";
        notice.classList.remove("error");
      }
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

  function thumbnailCacheKey(item, location) {
    const packId = String(location?.managed_pack_id || "").trim();
    if (!packId) return "";
    const digest = normalizeDigest(item?.sha256);
    if (digest) return JSON.stringify([packId, "sha256", digest]);
    const relativePath = String(item?.relative_path || "")
      .replace(/\\/g, "/")
      .replace(/^\/+/, "");
    if (relativePath) return JSON.stringify([packId, "path", relativePath]);
    return JSON.stringify([packId, "location", location.category, location.filename]);
  }

  function removeThumbnailCacheEntry(key) {
    const entry = thumbnailCache.get(key);
    if (!entry) return;
    thumbnailCache.delete(key);
    thumbnailCacheBytes = Math.max(0, thumbnailCacheBytes - entry.bytes);
  }

  function trimThumbnailCache() {
    while (
      thumbnailCache.size > THUMBNAIL_CACHE_MAX_ENTRIES ||
      thumbnailCacheBytes > THUMBNAIL_CACHE_MAX_BYTES
    ) {
      const oldestKey = thumbnailCache.keys().next().value;
      if (oldestKey === undefined) break;
      removeThumbnailCacheEntry(oldestKey);
    }
  }

  function rememberThumbnail(key, dataUrl, location) {
    const bytes = dataUrl.length * 2;
    if (bytes > THUMBNAIL_CACHE_MAX_BYTES) return;
    removeThumbnailCacheEntry(key);
    const entry = {
      dataUrl,
      bytes,
      packId: location.managed_pack_id,
      filename: location.filename,
    };
    thumbnailCache.set(key, entry);
    thumbnailCacheBytes += entry.bytes;
    trimThumbnailCache();
  }

  function readThumbnailCache(key) {
    const entry = thumbnailCache.get(key);
    if (!entry) return "";
    thumbnailCache.delete(key);
    thumbnailCache.set(key, entry);
    return entry.dataUrl;
  }

  function clearThumbnailCache() {
    thumbnailCache.clear();
    thumbnailRequests.clear();
    thumbnailCacheBytes = 0;
  }

  function evictThumbnailFile(packId, filename) {
    for (const [key, entry] of thumbnailCache) {
      if (entry.packId === packId && entry.filename === filename) removeThumbnailCacheEntry(key);
    }
    for (const [key, request] of thumbnailRequests) {
      if (request.packId === packId && request.filename === filename) thumbnailRequests.delete(key);
    }
  }

  function evictThumbnailItem(item, location = getImageLocation(item)) {
    const key = location ? thumbnailCacheKey(item, location) : "";
    if (!key) return;
    removeThumbnailCacheEntry(key);
    thumbnailRequests.delete(key);
  }

  async function getCachedThumbnail(item, location) {
    const key = thumbnailCacheKey(item, location);
    if (!key) throw new Error("缩略图缓存键无效");
    const cached = readThumbnailCache(key);
    if (cached) return cached;
    const activeRequest = thumbnailRequests.get(key);
    if (activeRequest) return activeRequest.promise;

    const request = {
      packId: location.managed_pack_id,
      filename: location.filename,
      promise: null,
    };
    request.promise = (async () => {
      const data = await apiGet("meme_image_data", { ...location, size: "preview" });
      const dataUrl = String(data?.data_url || "");
      if (!/^data:image\/[a-z0-9.+-]+;base64,/i.test(dataUrl)) {
        throw new Error("缩略图数据为空或格式无效");
      }
      if (thumbnailRequests.get(key) === request) rememberThumbnail(key, dataUrl, location);
      return dataUrl;
    })().finally(() => {
      if (thumbnailRequests.get(key) === request) thumbnailRequests.delete(key);
    });
    thumbnailRequests.set(key, request);
    return request.promise;
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
      const dataUrl = await getCachedThumbnail(item, location);
      image.src = dataUrl;
      card.classList.remove("thumbnail-loading");
      card.classList.add("thumbnail-loaded");
    } catch (error) {
      markThumbnailError(image, card);
    }
  }

  function normalizeDigest(value) {
    const digest = String(value || "").trim().toLowerCase();
    return /^[0-9a-f]{64}$/.test(digest) ? digest : "";
  }

  function selectionItem(item) {
    if (item?.duplicate) {
      const sha256 = normalizeDigest(item.sha256);
      return sha256 ? { kind: "duplicate", sha256 } : null;
    }
    const filename = String(item?.filename || "").trim();
    if (!filename) return null;
    return { kind: item.indexed ? "indexed" : "pending", filename };
  }

  function selectionKey(item) {
    if (!item || !["indexed", "pending", "duplicate"].includes(item.kind)) return "";
    if (item.kind === "duplicate") {
      const digest = normalizeDigest(item.sha256);
      return digest ? `duplicate:${digest}` : "";
    }
    const filename = String(item.filename || "").trim();
    return filename ? `${item.kind}:${filename}` : "";
  }

  function visibleSelectionItems(kind) {
    const source = kind === "indexed"
      ? (currentWorkspace?.indexed_items || [])
      : (currentWorkspace?.pending_items || []);
    return source.map(selectionItem).filter(Boolean);
  }

  function allSelected(items) {
    return items.length > 0 && items.every((item) => selectedItems.has(selectionKey(item)));
  }

  function updateSelectionUi() {
    const indexedVisible = visibleSelectionItems("indexed");
    const pendingVisible = visibleSelectionItems("pending");
    const indexedSelected = [...selectedItems.values()].filter((item) => item.kind === "indexed").length;
    const pendingSelected = selectedItems.size - indexedSelected;
    if (selectionModeButton) {
      selectionModeButton.textContent = selectionMode ? "退出批量选择" : "开启批量选择";
      selectionModeButton.setAttribute("aria-pressed", String(selectionMode));
      selectionModeButton.disabled = mutationInProgress;
    }
    if (selectionSummary) {
      selectionSummary.textContent = selectionMode
        ? `已整理 ${indexedSelected} 张，待处理 ${pendingSelected} 张`
        : "未开启批量选择";
    }
    if (selectIndexedPageButton) {
      selectIndexedPageButton.hidden = !selectionMode;
      selectIndexedPageButton.disabled = mutationInProgress || !indexedVisible.length;
      selectIndexedPageButton.textContent = allSelected(indexedVisible)
        ? "取消当前页已整理项"
        : "选择当前页已整理项";
    }
    if (selectPendingButton) {
      selectPendingButton.hidden = !selectionMode;
      selectPendingButton.disabled = mutationInProgress || !pendingVisible.length;
      selectPendingButton.textContent = allSelected(pendingVisible)
        ? "取消当前视图待处理项"
        : "选择当前视图待处理项";
    }
    if (clearSelectionButton) {
      clearSelectionButton.hidden = !selectionMode;
      clearSelectionButton.disabled = mutationInProgress || selectedItems.size === 0;
    }
    document.querySelectorAll(".card[data-selection-key]").forEach((card) => {
      const selected = selectionMode && selectedItems.has(card.dataset.selectionKey || "");
      card.classList.toggle("selection-mode", selectionMode);
      card.classList.toggle("selected", selected);
      card.querySelector(".card-preview")?.setAttribute("aria-pressed", String(Boolean(selected)));
    });
    document.querySelectorAll(".card-actions button").forEach((button) => {
      button.disabled = mutationInProgress;
    });
    renderPagination(currentWorkspace?.pagination);
  }

  function setSelectionMode(enabled) {
    selectionMode = Boolean(enabled);
    if (!selectionMode) selectedItems.clear();
    updateSelectionUi();
  }

  function toggleVisibleSelection(items) {
    const selectable = items.filter((item) => selectionKey(item));
    const remove = allSelected(selectable);
    selectable.forEach((item) => {
      const key = selectionKey(item);
      if (remove) selectedItems.delete(key);
      else selectedItems.set(key, item);
    });
    updateSelectionUi();
  }

  function toggleItemSelection(item) {
    const key = selectionKey(item);
    if (!key) return;
    if (selectedItems.has(key)) selectedItems.delete(key);
    else selectedItems.set(key, item);
    updateSelectionUi();
  }

  function disposalItemsForAction(item) {
    const key = selectionKey(item);
    if (!selectionMode || !key || !selectedItems.has(key)) return [item];
    const indexedAction = item.kind === "indexed";
    const matching = [...selectedItems.values()].filter((selected) =>
      indexedAction ? selected.kind === "indexed" : selected.kind !== "indexed"
    );
    return matching.length ? matching : [item];
  }

  async function goToIndexedPage(page) {
    currentPage = page;
    await loadWorkspace({ preserveSelection: true });
    indexedHeading?.focus?.({ preventScroll: true });
    indexedHeading?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }

  function renderPagination(paginationData = {}) {
    const indexed = paginationData.indexed || {};
    const totalPages = Math.max(1, Number(indexed.total_pages || 1));
    currentPage = Math.min(Math.max(1, Number(paginationData.page || currentPage)), totalPages);
    if (!pagination || !paginationPages || !paginationSummary) return;
    pagination.hidden = Number(indexed.total || 0) === 0;
    paginationPages.replaceChildren();
    if (pagination.hidden) return;

    paginationPrev.disabled = currentPage <= 1 || mutationInProgress;
    paginationNext.disabled = currentPage >= totalPages || mutationInProgress;
    const pageNumbers = new Set([1, totalPages, currentPage - 1, currentPage, currentPage + 1]);
    const visiblePages = [...pageNumbers]
      .filter((page) => page >= 1 && page <= totalPages)
      .sort((a, b) => a - b);
    let previousPage = 0;
    visiblePages.forEach((page) => {
      if (page - previousPage > 1) {
        const ellipsis = document.createElement("span");
        ellipsis.className = "capture-pagination-ellipsis";
        ellipsis.textContent = "…";
        paginationPages.append(ellipsis);
      }
      const button = document.createElement("button");
      button.type = "button";
      button.className = `capture-pagination-page${page === currentPage ? " active" : ""}`;
      button.textContent = String(page);
      button.setAttribute("aria-label", `第 ${page} 页`);
      button.setAttribute("aria-current", page === currentPage ? "page" : "false");
      button.disabled = page === currentPage || mutationInProgress;
      button.addEventListener("click", () => {
        void goToIndexedPage(page);
      });
      paginationPages.append(button);
      previousPage = page;
    });
    paginationSummary.textContent = `第 ${currentPage}/${totalPages} 页 · 已整理共 ${Number(indexed.total || 0)} 张`;
  }

  async function disposeCaptureItems(items, button) {
    const uniqueItems = new Map();
    (items || []).forEach((item) => {
      const key = selectionKey(item);
      if (key) uniqueItems.set(key, item);
    });
    if (!uniqueItems.size || !packSelect.value || mutationInProgress) return;
    const disposalItems = [...uniqueItems.values()];
    const indexedTotal = disposalItems.filter((item) => item.kind === "indexed").length;
    const pendingTotal = disposalItems.length - indexedTotal;
    const confirmation = [
      indexedTotal ? `已整理 ${indexedTotal} 张：删除文件并永久拉黑。` : "",
      pendingTotal ? `待处理 ${pendingTotal} 张：忽略并永久拉黑；普通项删除文件，重复项保留已有图片。` : "",
    ].filter(Boolean).join("\n");
    const confirmationPackId = packSelect.value;
    const confirmationGeneration = disposalOperationGeneration;
    if (!(await requestConfirmation(confirmation, "统一处理表情"))) return;
    if (
      confirmationGeneration !== disposalOperationGeneration ||
      packSelect.value !== confirmationPackId
    ) return;

    const disposalPackId = confirmationPackId;
    const disposalGeneration = ++disposalOperationGeneration;
    const isCurrentDisposal = () =>
      disposalGeneration === disposalOperationGeneration && packSelect.value === disposalPackId;
    button?.setAttribute("aria-busy", "true");
    mutationInProgress = true;
    updateSelectionUi();
    try {
      const result = await apiPost("capture/items/dispose", {
        pack_id: disposalPackId,
        items: disposalItems,
      });
      (result.succeeded || []).forEach((item) => {
        if (item.kind !== "duplicate") {
          evictThumbnailFile(disposalPackId, String(item.filename || ""));
        }
      });
      if (!isCurrentDisposal()) return;
      (result.succeeded || []).forEach((item) => {
        const key = selectionKey(item);
        selectedItems.delete(key);
        failedDisposals.delete(key);
      });
      (result.failed || []).forEach((item) => {
        const key = selectionKey(item);
        if (key) failedDisposals.set(key, item);
      });
      await loadWorkspace({ preserveSelection: true });
      if (!isCurrentDisposal()) return;
      const failedCount = Number(result.failed_count || 0);
      notice.textContent = failedCount
        ? `已处理 ${Number(result.disposed_count || 0)} 项，${failedCount} 项失败；失败项仍保持选中。`
        : result.message || "统一处理完成";
      notice.classList.toggle("error", failedCount > 0);
    } catch (error) {
      if (isCurrentDisposal()) showError(error);
    } finally {
      if (disposalGeneration === disposalOperationGeneration) {
        mutationInProgress = false;
        button?.setAttribute("aria-busy", "false");
        updateSelectionUi();
      }
    }
  }

  function renderCard(item, target) {
    const disposal = selectionItem(item);
    const disposalKey = selectionKey(disposal);
    const failed = failedDisposals.get(disposalKey);
    const card = document.createElement("article");
    card.className = `card thumbnail-loading${item.duplicate ? " duplicate" : ""}${failed ? " disposal-failed" : ""}`;
    card.dataset.category = item.category || item.tag || "";
    card.dataset.filename = item.filename || "";
    card.dataset.selectionKey = disposalKey;
    const digest = normalizeDigest(item.sha256);
    const thumbnailLocation = getImageLocation(item);
    if (item.duplicate && digest) card.dataset.sha256 = digest;

    card.title = item.filename || "未命名图片";
    const previewButton = document.createElement("button");
    previewButton.type = "button";
    previewButton.className = "card-preview";
    previewButton.setAttribute("aria-label", `预览 ${item.filename || "图片"}`);
    previewButton.setAttribute("aria-pressed", "false");
    const thumbnail = document.createElement("span");
    thumbnail.className = "card-thumbnail";
    thumbnail.setAttribute("aria-hidden", "true");
    const image = document.createElement("img");
    image.className = "thumbnail-image";
    image.loading = "lazy";
    image.alt = "";
    image.addEventListener("error", () => {
      evictThumbnailItem(item, thumbnailLocation);
      markThumbnailError(image, card);
    });
    const placeholder = document.createElement("span");
    placeholder.className = "thumbnail-placeholder";
    placeholder.textContent = "加载缩略图";
    const errorText = document.createElement("span");
    errorText.className = "thumbnail-error-text";
    errorText.textContent = "缩略图加载失败，点击重试";
    thumbnail.append(image, placeholder, errorText);
    const title = document.createElement("strong");
    title.textContent = item.filename || "未命名图片";
    const tagList = document.createElement("span");
    tagList.className = "card-tags";
    const tags = Array.isArray(item.tags) && item.tags.length
      ? item.tags
      : [item.category || item.tag || "未分类"];
    tags.forEach((tag) => {
      const tagBadge = document.createElement("span");
      tagBadge.className = "card-tag";
      tagBadge.textContent = tag;
      tagList.append(tagBadge);
    });
    const meta = document.createElement("span");
    meta.className = "card-status";
    meta.textContent = failed?.blacklisted
      ? "已拦截、删除失败"
      : item.duplicate ? "重复待去重" : item.indexed ? "已索引" : "待分类";
    const description = document.createElement("small");
    description.textContent = failed?.reason || item.description || "点击查看图片";
    previewButton.append(thumbnail, title, tagList, meta, description);
    const actions = document.createElement("div");
    actions.className = "card-actions";
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    if (item.duplicate) {
      deleteButton.className = "card-ignore";
      deleteButton.textContent = "忽略并拉黑";
      deleteButton.setAttribute("aria-label", `忽略并拉黑 ${item.filename || "图片"} 的重复记录`);
      deleteButton.title = "忽略并永久拉黑；仅隐藏重复记录，保留已有图片";
    } else if (item.indexed) {
      deleteButton.className = "card-delete";
      deleteButton.innerHTML = `
        <svg class="card-delete-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d="M9 3h6l1 2h4v2H4V5h4l1-2Zm-3 6h12l-.7 10.4A2.8 2.8 0 0 1 14.5 22h-5a2.8 2.8 0 0 1-2.8-2.6L6 9Zm3 2v7h2v-7H9Zm4 0v7h2v-7h-2Z" />
        </svg><span>删除并拉黑</span>`;
      deleteButton.setAttribute("aria-label", `删除并拉黑 ${item.filename || "图片"}`);
      deleteButton.title = "删除文件并加入永久黑名单";
    } else {
      deleteButton.className = "card-ignore";
      deleteButton.textContent = "忽略并拉黑";
      deleteButton.setAttribute("aria-label", `忽略并拉黑 ${item.filename || "图片"}`);
      deleteButton.title = "忽略并永久拉黑；同时删除未分类文件";
    }
    deleteButton.addEventListener("click", (event) => {
      event.stopPropagation();
      void disposeCaptureItems(disposalItemsForAction(disposal), deleteButton);
    });
    actions.append(deleteButton);
    card.append(previewButton, actions);
    target.append(card);
    card.addEventListener("click", (event) => {
      if (event.target !== card) return;
      if (selectionMode && disposal) {
        toggleItemSelection(disposal);
        return;
      }
      if (card.classList.contains("thumbnail-error")) {
        void loadThumbnail(item, image, card);
      } else {
        void showPreview(item);
      }
    });
    previewButton.addEventListener("click", () => {
      if (selectionMode && disposal) {
        toggleItemSelection(disposal);
        return;
      }
      if (card.classList.contains("thumbnail-error")) {
        void loadThumbnail(item, image, card);
        return;
      }
      void showPreview(item);
    });
    void loadThumbnail(item, image, card);
  }

  function renderWorkspace(data) {
    currentWorkspace = data;
    currentPage = Number(data.pagination?.page || currentPage);
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
      const labelElement = document.createElement("span");
      labelElement.textContent = label;
      const valueElement = document.createElement("strong");
      valueElement.textContent = String(value);
      item.append(labelElement, valueElement);
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
      currentPage = 1;
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
        currentPage = 1;
        void loadWorkspace();
      });
      categoryFilters.append(button);
    }

    const indexed = data.indexed_items || [];
    const pending = data.pending_items || [];
    indexedCount.textContent = `${stats.indexed || 0} 张`;
    pendingCount.textContent = `${(stats.pending || 0) + (stats.duplicate || 0)} 条`;
    indexedItems.replaceChildren();
    pendingItems.replaceChildren();
    if (indexed.length) indexed.forEach((item) => renderCard(item, indexedItems));
    else renderEmpty(indexedItems, "暂无已完成的偷取索引");
    if (pending.length) pending.forEach((item) => renderCard(item, pendingItems));
    else renderEmpty(pendingItems, "当前没有待处理偷取图片");
    renderPagination(data.pagination);

    const state = data.library_index || {};
    const indexInProgress = indexing || ["queued", "running"].includes(state.status);
    indexButton.disabled =
      indexInProgress || !state.active_pack || !(stats.pending || stats.duplicate);
    indexButton.textContent = indexInProgress ? "分类索引中……" : "分类索引待处理项";
    reindexButton.disabled = reindexing || indexing;
    notice.textContent = indexing && state.status === "idle"
      ? "已提交分类索引，正在启动……"
      : state.message || "目录索引已加载";
    notice.classList.remove("error");
  }

  async function loadWorkspace({ preserveSelection = false } = {}) {
    const packId = packSelect.value;
    if (!packId) return;
    const generation = ++workspaceRequestGeneration;
    if (!preserveSelection) {
      selectionMode = false;
      selectedItems.clear();
      failedDisposals.clear();
    }
    try {
      const params = { pack_id: packId };
      if (selectedCategory) params.category = selectedCategory;
      params.page = currentPage;
      const data = await apiGet("capture/workspace", params);
      if (generation !== workspaceRequestGeneration || packSelect.value !== packId) return;
      renderWorkspace(data);
      updateSelectionUi();
      return data;
    } catch (error) {
      if (generation !== workspaceRequestGeneration || packSelect.value !== packId) return;
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
    closeConfirmation(false);
    reindexPollGeneration += 1;
    disposalOperationGeneration += 1;
    mutationInProgress = false;
    clearThumbnailCache();
    stopReindexPolling();
    stopIndexPolling();
    selectedCategory = "";
    currentPage = 1;
    setSelectionMode(false);
    reindexing = false;
    indexing = false;
    reindexButton.setAttribute("aria-busy", "false");
    reindexProgress.hidden = true;
    progressRow.classList.remove("active");
    void loadWorkspace();
  });
  refreshButton.addEventListener("click", () => void loadWorkspace());
  paginationPrev?.addEventListener("click", () => {
    if (currentPage > 1) {
      void goToIndexedPage(currentPage - 1);
    }
  });
  paginationNext?.addEventListener("click", () => {
    const totalPages = Math.max(1, Number(currentWorkspace?.pagination?.indexed?.total_pages || 1));
    if (currentPage < totalPages) {
      void goToIndexedPage(currentPage + 1);
    }
  });
  selectionModeButton?.addEventListener("click", () => setSelectionMode(!selectionMode));
  selectIndexedPageButton?.addEventListener("click", () => {
    if (!mutationInProgress) toggleVisibleSelection(visibleSelectionItems("indexed"));
  });
  selectPendingButton?.addEventListener("click", () => {
    if (!mutationInProgress) toggleVisibleSelection(visibleSelectionItems("pending"));
  });
  clearSelectionButton?.addEventListener("click", () => {
    selectedItems.clear();
    updateSelectionUi();
  });
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
    if (indexing || !packSelect.value) return;
    if (!(await requestConfirmation(
      "将扫描整个资源包并整理旧目录；完整 v4 索引会跳过视觉模型，旧版或字段不完整的图片会重新调用视觉模型。继续吗？",
      "全量语义重索引",
    ))) return;
    const reindexPackId = packSelect.value;
    const generation = ++reindexPollGeneration;
    reindexing = true;
    reindexButton.disabled = true;
    reindexButton.setAttribute("aria-busy", "true");
    notice.classList.remove("error");
    notice.textContent = "正在进行全量语义重索引，请稍候……";
    try {
      const result = await apiPost("capture/reindex", { pack_id: reindexPackId });
      if (generation !== reindexPollGeneration || packSelect.value !== reindexPackId) return;
      renderReindexProgress(result);
      void pollReindexStatus(generation);
    } catch (error) {
      if (generation !== reindexPollGeneration || packSelect.value !== reindexPackId) return;
      reindexing = false;
      reindexButton.disabled = false;
      reindexButton.setAttribute("aria-busy", "false");
      showError(error);
    }
  });
  confirmCancel.addEventListener("click", () => closeConfirmation(false));
  confirmConfirm.addEventListener("click", () => closeConfirmation(true));
  confirmMask.addEventListener("click", (event) => {
    if (event.target === confirmMask) closeConfirmation(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !confirmMask.classList.contains("hidden")) {
      closeConfirmation(false);
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
