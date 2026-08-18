async function initCaptureIndexPage() {
  const pageApi = window.AstrBotPluginPage;
  const packSelect = document.querySelector("#pack");
  const notice = document.querySelector("#notice");
  const items = document.querySelector("#capture-items");
  const itemsCount = document.querySelector("#capture-items-count");
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
  const selectIndexButton = document.querySelector("#capture-select-index-button");
  const clearSelectionButton = document.querySelector("#capture-clear-selection-button");
  const ignoreAllButton = document.querySelector("#capture-ignore-all-button");
  const selectionSummary = document.querySelector("#capture-selection-summary");
  const itemsHeading = document.querySelector("#capture-items-heading");
  const viewFilters = [...document.querySelectorAll("[data-capture-view]")];
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
  const exportButton = document.querySelector("#capture-export-button");
  const importButton = document.querySelector("#capture-import-button");
  const importFileInput = document.querySelector("#capture-import-file");
  const exportBackupCheckbox = document.querySelector("#capture-export-backup");
  const exportHint = document.querySelector("#capture-export-hint");
  const importPreview = document.querySelector("#capture-import-preview");
  const importPreviewName = document.querySelector("#capture-import-preview-name");
  const importPreviewMeta = document.querySelector("#capture-import-preview-meta");
  const importSetDefault = document.querySelector("#capture-import-set-default");
  const importConfirmButton = document.querySelector("#capture-import-confirm-button");
  const importCancelButton = document.querySelector("#capture-import-cancel-button");
  const transferMessage = document.querySelector("#capture-transfer-message");
  let selectedCategory = "";
  let reindexing = false;
  let indexing = false;
  let pendingConfirmation = null;
  let currentWorkspace = null;
  let selectionMode = false;
  const selectedItems = new Map();
  const failedDisposals = new Map();
  let mutationInProgress = false;
  let disposalOperationGeneration = 0;
  let currentPage = 1;
  let currentView = "all";
  let workspaceRequestGeneration = 0;
  const THUMBNAIL_CACHE_MAX_ENTRIES = 512;
  const THUMBNAIL_CACHE_MAX_BYTES = 64 * 1024 * 1024;
  const thumbnailCache = new Map();
  const thumbnailRequests = new Map();
  let thumbnailCacheBytes = 0;
  let pendingImportToken = "";
  let exportCapabilityRequestId = 0;

  if (!pageApi) {
    notice.textContent = "请从 AstrBot WebUI 的插件页面打开表情索引。";
    return;
  }

  await pageApi.ready();

  const apiGet = (path, params = {}) => pageApi.apiGet(path, params);
  const apiPost = (path, body = {}) => pageApi.apiPost(path, body);
  function createPollingController() {
    let timer = null;
    let generation = 0;
    return {
      nextGeneration() {
        generation += 1;
        return generation;
      },
      current() {
        return generation;
      },
      isCurrent(value) {
        return value === generation;
      },
      schedule(callback, delay = 500) {
        if (timer !== null) window.clearTimeout(timer);
        timer = window.setTimeout(() => {
          timer = null;
          callback();
        }, delay);
      },
      stop() {
        if (timer !== null) window.clearTimeout(timer);
        timer = null;
        generation += 1;
      },
    };
  }
  const reindexPolling = createPollingController();
  const indexPolling = createPollingController();
  function setTaskBusy(button, busy) {
    if (!button) return;
    button.disabled = Boolean(busy);
    button.setAttribute("aria-busy", String(Boolean(busy)));
  }
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

  function setView(view) {
    const allowed = new Set(["all", "classified", "unclassified"]);
    const nextView = allowed.has(view) ? view : "all";
    currentView = currentView === nextView ? "all" : nextView;
    currentPage = 1;
    void loadWorkspace();
  }

  async function pollReindexStatus(generation = reindexPolling.current()) {
    const packId = packSelect.value;
    if (!packId) return;
    try {
      const state = await apiGet("capture/reindex/status", { pack_id: packId });
      if (!reindexPolling.isCurrent(generation) || packSelect.value !== packId) return;
      renderReindexProgress(state);
      if (["queued", "running"].includes(state.status)) {
        reindexing = true;
        setTaskBusy(reindexButton, true);
        reindexPolling.schedule(() => void pollReindexStatus(generation));
        return;
      }
      if (state.status === "error") {
        reindexing = false;
        setTaskBusy(reindexButton, false);
        showError(new Error(state.message || "重索引失败"));
        return;
      }
      if (["completed", "completed_with_errors"].includes(state.status)) {
        const shouldClearThumbnails = reindexing;
        reindexing = false;
        setTaskBusy(reindexButton, false);
        if (shouldClearThumbnails) clearThumbnailCache();
        const refreshed = await loadWorkspace();
        if (!reindexPolling.isCurrent(generation) || packSelect.value !== packId) return;
        if (refreshed) {
          const completedWithErrors = state.status === "completed_with_errors";
          notice.textContent = completedWithErrors ? (state.message || "重索引完成，但存在失败项") : "";
          notice.classList.toggle("error", completedWithErrors);
        }
        return;
      }
      reindexing = false;
      setTaskBusy(reindexButton, false);
    } catch (error) {
      if (!reindexPolling.isCurrent(generation) || packSelect.value !== packId) return;
      reindexing = false;
      setTaskBusy(reindexButton, false);
      showError(error);
    }
  }

  async function pollIndexStatus(generation = indexPolling.current()) {
    const packId = packSelect.value;
    if (!packId || !indexing) return;
    try {
      const state = await apiGet("capture/index/status", { pack_id: packId });
      if (!indexPolling.isCurrent(generation) || packSelect.value !== packId) return;
      if (["queued", "running"].includes(state.status)) {
        notice.textContent = state.message || "分类索引处理中……";
        notice.classList.remove("error");
        setTaskBusy(indexButton, true);
        indexPolling.schedule(() => void pollIndexStatus(generation));
        return;
      }
      indexing = false;
      setTaskBusy(indexButton, false);
      if (state.status === "error") {
        showError(new Error(state.message || "分类索引失败"));
        return;
      }
      const data = await loadWorkspace();
      if (data && indexPolling.isCurrent(generation) && packSelect.value === packId) {
        notice.textContent = state.message || "分类索引已完成";
        notice.classList.remove("error");
      }
    } catch (error) {
      if (!indexPolling.isCurrent(generation) || packSelect.value !== packId) return;
      indexing = false;
      setTaskBusy(indexButton, false);
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
    const kind = item.indexed ? "indexed" : "pending";
    const digest = normalizeDigest(item.sha256);
    return kind === "pending" && digest
      ? { kind, filename, sha256: digest }
      : { kind, filename };
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
    const source = currentWorkspace?.items || [];
    const visible = kind === "indexed"
      ? source.filter((item) => item.indexed && !item.duplicate)
      : source.filter((item) => !item.indexed || item.duplicate);
    return visible.map(selectionItem).filter(Boolean);
  }

  function allSelected(items) {
    return items.length > 0 && items.every((item) => selectedItems.has(selectionKey(item)));
  }

  function updateSelectionUi() {
    const indexedVisible = visibleSelectionItems("indexed");
    const pendingVisible = visibleSelectionItems("pending");
    const indexedSelected = [...selectedItems.values()].filter((item) => item.kind === "indexed").length;
    const pendingSelected = [...selectedItems.values()].filter((item) => item.kind === "pending").length;
    const duplicateSelected = [...selectedItems.values()].filter((item) => item.kind === "duplicate").length;
    if (selectionModeButton) {
      selectionModeButton.textContent = selectionMode ? "退出批量选择" : "开启批量选择";
      selectionModeButton.setAttribute("aria-pressed", String(selectionMode));
      selectionModeButton.disabled = mutationInProgress;
    }
    if (selectionSummary) {
      selectionSummary.textContent = selectionMode
        ? `已整理 ${indexedSelected} 张，待处理 ${pendingSelected} 张，待忽略 ${duplicateSelected} 条`
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
    if (selectIndexButton) {
      selectIndexButton.hidden = !selectionMode;
      selectIndexButton.disabled = mutationInProgress || indexing || pendingSelected === 0;
    }
    if (ignoreAllButton) {
      const stats = currentWorkspace?.summary || {};
      ignoreAllButton.disabled = mutationInProgress ||
        Number(stats.pending || 0) + Number(stats.duplicate || 0) === 0;
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
    if (item.kind !== "indexed") return [item];
    const matching = [...selectedItems.values()].filter((selected) => selected.kind === "indexed");
    return matching.length ? matching : [item];
  }

  async function goToItemsPage(page) {
    currentPage = page;
    await loadWorkspace({ preserveSelection: true });
    itemsHeading?.focus?.({ preventScroll: true });
    itemsHeading?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }

  function renderPagination(paginationData = {}) {
    const visibleItems = paginationData.items || paginationData.indexed || {};
    const totalPages = Math.max(1, Number(visibleItems.total_pages || 1));
    currentPage = Math.min(Math.max(1, Number(paginationData.page || currentPage)), totalPages);
    if (!pagination || !paginationPages || !paginationSummary) return;
    pagination.hidden = Number(visibleItems.total || 0) === 0;
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
        void goToItemsPage(page);
      });
      paginationPages.append(button);
      previousPage = page;
    });
    paginationSummary.textContent = `第 ${currentPage}/${totalPages} 页 · 当前视图共 ${Number(visibleItems.total || 0)} 张`;
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

  async function indexSelectedItems() {
    if (!selectionMode || indexing || !packSelect.value || mutationInProgress) return;
    const selectedPending = [...selectedItems.values()]
      .filter((item) => item.kind === "pending" && normalizeDigest(item.sha256));
    if (!selectedPending.length) return;
    const confirmation = `将分类索引选中的 ${selectedPending.length} 张待处理表情；重复待忽略项不会参与，其他图片保持不变。`;
    if (!(await requestConfirmation(confirmation, "选择索引"))) return;
    const packId = packSelect.value;
    const generation = indexPolling.nextGeneration();
    indexing = true;
    selectIndexButton.disabled = true;
    setTaskBusy(indexButton, true);
    try {
      const result = await apiPost("capture/index", {
        pack_id: packId,
        items: selectedPending.map((item) => ({
          kind: "pending",
          filename: item.filename,
          sha256: normalizeDigest(item.sha256),
        })),
      });
      if (!indexPolling.isCurrent(generation) || packSelect.value !== packId) return;
      selectedPending.forEach((item) => selectedItems.delete(selectionKey(item)));
      notice.textContent = result.message || "已开始索引选中的待处理表情";
      await loadWorkspace({ preserveSelection: true });
      void pollIndexStatus(generation);
    } catch (error) {
      if (!indexPolling.isCurrent(generation) || packSelect.value !== packId) return;
      indexing = false;
      await loadWorkspace({ preserveSelection: true });
      showError(error);
    } finally {
      updateSelectionUi();
    }
  }

  async function ignoreAllCaptureItems() {
    if (!packSelect.value || mutationInProgress) return;
    const stats = currentWorkspace?.summary || {};
    const pendingTotal = Number(stats.pending || 0);
    const duplicateTotal = Number(stats.duplicate || 0);
    const total = pendingTotal + duplicateTotal;
    if (!total) return;
    if (!(await requestConfirmation(
      `将忽略当前资源包全部 ${pendingTotal} 张待处理和 ${duplicateTotal} 条待忽略记录，并永久加入黑名单。其他已索引表情不受影响。继续吗？`,
      "一键忽略全部",
    ))) return;
    const packId = packSelect.value;
    const generation = ++disposalOperationGeneration;
    mutationInProgress = true;
    ignoreAllButton.setAttribute("aria-busy", "true");
    updateSelectionUi();
    try {
      const result = await apiPost("capture/items/ignore-all", { pack_id: packId });
      if (generation !== disposalOperationGeneration || packSelect.value !== packId) return;
      for (const [key, item] of selectedItems) {
        if (item.kind !== "indexed") selectedItems.delete(key);
      }
      clearThumbnailCache();
      await loadWorkspace({ preserveSelection: true });
      notice.textContent = result.message || "已忽略全部待处理和待忽略表情";
      notice.classList.remove("error");
    } catch (error) {
      if (generation === disposalOperationGeneration) showError(error);
    } finally {
      if (generation === disposalOperationGeneration) {
        mutationInProgress = false;
        ignoreAllButton.setAttribute("aria-busy", "false");
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
    card.dataset.kind = item.duplicate ? "duplicate" : item.indexed ? "indexed" : "pending";
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
    const fallbackItems = [
      ...(data.indexed_items || []),
      ...(data.pending_items || []),
    ];
    currentWorkspace = {
      ...data,
      items: Array.isArray(data.items) ? data.items : fallbackItems,
    };
    currentPage = Number(data.pagination?.page || currentPage);
    const stats = data.summary || {};

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

    const viewLabels = {
      all: "全部表情",
      classified: "已分类",
      unclassified: "未分类",
    };
    const visibleItems = currentWorkspace.items;
    const totalItems = Number(data.pagination?.items?.total ?? visibleItems.length);
    viewFilters.forEach((button) => {
      const active = button.dataset.captureView === currentView;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    itemsHeading.textContent = viewLabels[currentView] || viewLabels.all;
    itemsCount.textContent = `${totalItems} 张`;
    items.replaceChildren();
    if (visibleItems.length) {
      visibleItems.forEach((item) => renderCard(item, items));
    } else {
      const emptyMessage = currentView === "unclassified"
        ? "当前没有未分类表情"
        : currentView === "classified"
          ? "当前没有已分类表情"
          : "当前没有表情";
      renderEmpty(items, emptyMessage);
    }
    renderPagination(data.pagination);

    const state = data.library_index || {};
    const indexInProgress = indexing || ["queued", "running"].includes(state.status);
    setTaskBusy(indexButton, indexInProgress);
    indexButton.disabled = indexInProgress || !state.active_pack || !(stats.pending);
    indexButton.textContent = indexInProgress ? "分类索引中……" : "分类索引待处理项";
    setTaskBusy(reindexButton, reindexing);
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
      params.view = currentView;
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
    const preferredPackId = new URLSearchParams(window.location?.search || "").get("managed_pack_id") || "";
    packSelect.replaceChildren();
    for (const pack of data.packs || []) {
      const option = document.createElement("option");
      option.value = String(pack.id || "");
      option.textContent = `${pack.name || pack.id || "未命名资源包"} (${pack.id || "-"})`;
      packSelect.append(option);
    }
    if ((data.packs || []).some((pack) => String(pack.id || "") === preferredPackId)) {
      packSelect.value = preferredPackId;
    }
  }

  function setTransferMessage(message, type = "") {
    if (!transferMessage) return;
    transferMessage.textContent = String(message || "");
    transferMessage.classList.toggle("success", type === "success");
    transferMessage.classList.toggle("error", type === "error");
  }

  async function refreshExportCapability() {
    const packId = String(packSelect?.value || "").trim();
    const requestId = ++exportCapabilityRequestId;
    if (!packId) {
      if (exportBackupCheckbox) exportBackupCheckbox.disabled = true;
      if (exportHint) exportHint.textContent = "当前没有可导出的资源包。";
      return;
    }
    if (exportHint) exportHint.textContent = "正在检查导出能力…";
    try {
      const status = await apiGet("packs/export/status", { pack_id: packId });
      if (requestId !== exportCapabilityRequestId) return;
      const available = Boolean(status?.vector_backup_available);
      if (exportBackupCheckbox) exportBackupCheckbox.disabled = !available;
      if (!available && exportBackupCheckbox) exportBackupCheckbox.checked = false;
      if (exportHint) {
        exportHint.textContent = available
          ? "保留语义数据，仅适合本机恢复。"
          : "当前资源包没有完整语义数据，仅支持分享版。";
      }
    } catch (error) {
      if (requestId !== exportCapabilityRequestId) return;
      if (exportBackupCheckbox) exportBackupCheckbox.disabled = true;
      if (exportHint) exportHint.textContent = "暂时无法读取导出能力，默认使用分享版。";
    }
  }

  async function exportCurrentPack() {
    const packId = String(packSelect?.value || "").trim();
    if (!packId) {
      setTransferMessage("当前没有可导出的资源包。", "error");
      return;
    }
    const mode = exportBackupCheckbox?.checked ? "backup" : "share";
    setTransferMessage("正在生成压缩包，请不要关闭页面。");
    try {
      await pageApi.download("packs/export/download", { pack_id: packId, mode });
      setTransferMessage(
        mode === "backup"
          ? "带向量自用备份已生成，已开始下载。"
          : "分享版已生成，已开始下载。",
        "success",
      );
    } catch (error) {
      setTransferMessage(error?.message || String(error), "error");
    }
  }

  function resetImportPreview() {
    pendingImportToken = "";
    if (importFileInput) importFileInput.value = "";
    importPreview?.classList.add("hidden");
    if (importPreviewName) importPreviewName.textContent = "";
    if (importPreviewMeta) importPreviewMeta.textContent = "";
    if (importSetDefault) importSetDefault.checked = false;
  }

  async function stageImportFile(file) {
    if (!file) return;
    if (!String(file.name || "").toLowerCase().endsWith(".zip")) {
      setTransferMessage("请选择 zip 格式的表情包。", "error");
      return;
    }
    pendingImportToken = "";
    setTransferMessage("正在检查压缩包结构和兼容性…");
    try {
      const data = await pageApi.upload("packs/import/stage", file);
      pendingImportToken = String(data?.import_token || "").trim();
      if (!pendingImportToken) {
        throw new Error("服务器没有返回导入凭证");
      }
      const formatLabels = {
        v2: data?.export_mode === "backup" ? "新版带向量备份" : "新版分享包",
        v1: "兼容版资源包",
        legacy: "旧版无语义包 · 将自动转换",
      };
      if (importPreviewName) {
        importPreviewName.textContent =
          `${data?.name || data?.pack_id || "待导入表情包"} (${data?.pack_id || "未知 ID"})`;
      }
      if (importPreviewMeta) {
        const format = formatLabels[data?.detected_format] || "已识别的表情包";
        const vectors = data?.vectors_present ? "，含向量将校验" : "";
        importPreviewMeta.textContent =
          `${format} · ${Number(data?.image_count || 0)} 张图片 · ${Number(data?.category_count || 0)} 个分类${vectors}`;
      }
      importPreview?.classList.remove("hidden");
      setTransferMessage("检查完成，请确认导入选项。", "success");
    } catch (error) {
      resetImportPreview();
      setTransferMessage(error?.message || String(error), "error");
    }
  }

  async function confirmPackImport() {
    if (!pendingImportToken) {
      setTransferMessage("请先选择并检查压缩包。", "error");
      return;
    }
    setTransferMessage("正在安装表情包，请不要关闭页面。");
    if (importConfirmButton) importConfirmButton.disabled = true;
    try {
      const data = await apiPost("packs/import/apply", {
        import_token: pendingImportToken,
        overwrite: false,
        overwrite_manual_semantics: false,
        set_as_default: Boolean(importSetDefault?.checked),
      });
      const importedPackId = String(data?.pack_id || "").trim();
      const vectorHint = data?.vectors_restored
        ? "，向量已恢复"
        : data?.vector_warning
          ? `；${data.vector_warning}`
          : "";
      resetImportPreview();
      setTransferMessage(`已导入 ${data?.name || importedPackId}${vectorHint}`, "success");
      await loadPacks();
      await loadWorkspace();
      void refreshExportCapability();
    } catch (error) {
      setTransferMessage(error?.message || String(error), "error");
    } finally {
      if (importConfirmButton) importConfirmButton.disabled = false;
    }
  }

  packSelect.addEventListener("change", () => {
    closeConfirmation(false);
    reindexPolling.stop();
    indexPolling.stop();
    disposalOperationGeneration += 1;
    mutationInProgress = false;
    clearThumbnailCache();
    selectedCategory = "";
    currentView = "all";
    currentPage = 1;
    setSelectionMode(false);
    reindexing = false;
    indexing = false;
    setTaskBusy(reindexButton, false);
    setTaskBusy(indexButton, false);
    reindexProgress.hidden = true;
    progressRow.classList.remove("active");
    void loadWorkspace();
    void refreshExportCapability();
  });
  refreshButton.addEventListener("click", () => void loadWorkspace());
  exportButton?.addEventListener("click", () => void exportCurrentPack());
  importButton?.addEventListener("click", () => importFileInput?.click());
  importFileInput?.addEventListener("change", () => {
    void stageImportFile(importFileInput.files?.[0]);
  });
  importConfirmButton?.addEventListener("click", () => void confirmPackImport());
  importCancelButton?.addEventListener("click", () => {
    resetImportPreview();
    setTransferMessage("");
  });
  viewFilters.forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.captureView || "all"));
  });
  paginationPrev?.addEventListener("click", () => {
    if (currentPage > 1) {
      void goToItemsPage(currentPage - 1);
    }
  });
  paginationNext?.addEventListener("click", () => {
    const paginationData = currentWorkspace?.pagination || {};
    const totalPages = Math.max(1, Number(
      (paginationData.items || paginationData.indexed || {}).total_pages || 1,
    ));
    if (currentPage < totalPages) {
      void goToItemsPage(currentPage + 1);
    }
  });
  selectionModeButton?.addEventListener("click", () => setSelectionMode(!selectionMode));
  selectIndexedPageButton?.addEventListener("click", () => {
    if (!mutationInProgress) toggleVisibleSelection(visibleSelectionItems("indexed"));
  });
  selectPendingButton?.addEventListener("click", () => {
    if (!mutationInProgress) toggleVisibleSelection(visibleSelectionItems("pending"));
  });
  selectIndexButton?.addEventListener("click", () => void indexSelectedItems());
  ignoreAllButton?.addEventListener("click", () => void ignoreAllCaptureItems());
  clearSelectionButton?.addEventListener("click", () => {
    selectedItems.clear();
    updateSelectionUi();
  });
  indexButton.addEventListener("click", async () => {
    if (indexing || !packSelect.value) return;
    const indexPackId = packSelect.value;
    const generation = indexPolling.nextGeneration();
    indexing = true;
    setTaskBusy(indexButton, true);
    try {
      const result = await apiPost("capture/index", { pack_id: indexPackId });
      if (!indexPolling.isCurrent(generation) || packSelect.value !== indexPackId) return;
      notice.textContent = result.message || "分类索引已开始";
      await loadWorkspace();
      void pollIndexStatus(generation);
    } catch (error) {
      if (!indexPolling.isCurrent(generation) || packSelect.value !== indexPackId) return;
      indexing = false;
      await loadWorkspace();
      showError(error);
    }
  });
  reindexButton.addEventListener("click", async () => {
    if (indexing || !packSelect.value) return;
    if (!(await requestConfirmation(
      "将扫描整个资源包并整理旧目录；旧版或字段不完整的图片会重新调用视觉模型。继续吗？",
      "全量语义重索引",
    ))) return;
    const reindexPackId = packSelect.value;
    const generation = reindexPolling.nextGeneration();
    reindexing = true;
    setTaskBusy(reindexButton, true);
    notice.classList.remove("error");
    notice.textContent = "正在进行全量语义重索引，请稍候……";
    try {
      const result = await apiPost("capture/reindex", { pack_id: reindexPackId });
      if (!reindexPolling.isCurrent(generation) || packSelect.value !== reindexPackId) return;
      renderReindexProgress(result);
      void pollReindexStatus(generation);
    } catch (error) {
      if (!reindexPolling.isCurrent(generation) || packSelect.value !== reindexPackId) return;
      reindexing = false;
      setTaskBusy(reindexButton, false);
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
    await refreshExportCapability();
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
