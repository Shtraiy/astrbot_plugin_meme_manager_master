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
  const ignoreDuplicatesButton = document.querySelector("#capture-ignore-duplicates-button");
  const selectionModeButton = document.querySelector("#capture-selection-mode-button");
  const selectVisibleDuplicatesButton = document.querySelector("#capture-select-visible-duplicates-button");
  const ignoreSelectedButton = document.querySelector("#capture-ignore-selected-button");
  const selectionSummary = document.querySelector("#capture-selection-summary");
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
  let indexing = false;
  let indexPollTimer = null;
  let pendingConfirmation = null;
  let currentWorkspace = null;
  let selectionMode = false;
  const selectedDuplicateDigests = new Set();
  let mutationInProgress = false;
  let currentPage = 1;

  if (!pageApi) {
    notice.textContent = "请从 AstrBot WebUI 的插件页面打开表情索引。";
    return;
  }

  await pageApi.ready();
  const allowedPages = new Set(["a_manage", "catalog", "settings", "semantic"]);
  document.querySelectorAll("a[data-nav-page]").forEach((link) => {
    const pageName = link.getAttribute("data-nav-page");
    if (!pageName || !allowedPages.has(pageName)) return;
    const currentParams = new URLSearchParams(window.location.search);
    const navView = link.getAttribute("data-nav-view") || "";
    if (navView) {
      currentParams.set("view", navView);
    } else {
      currentParams.delete("view");
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
    link.target = "_top";
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
    return {
      managed_pack_id: packSelect.value,
      category,
      filename,
    };
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
      const data = await apiGet("meme_image_data", {
        ...location,
        size: "preview",
      });
      if (!data.data_url) throw new Error("缩略图数据为空");
      image.src = data.data_url;
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

  function getVisibleDuplicateDigests() {
    return uniqueDuplicateDigests(currentWorkspace?.pending_items || []);
  }

  function updateSelectionUi() {
    const visibleDigests = getVisibleDuplicateDigests();
    const allVisibleSelected = visibleDigests.length > 0 && visibleDigests.every((digest) => selectedDuplicateDigests.has(digest));
    if (selectionModeButton) {
      selectionModeButton.textContent = selectionMode ? "退出批量选择" : "开启批量选择";
      selectionModeButton.setAttribute("aria-pressed", String(selectionMode));
      selectionModeButton.disabled = mutationInProgress;
    }
    if (selectionSummary) {
      selectionSummary.textContent = selectionMode
        ? `已选择 ${selectedDuplicateDigests.size} 项重复记录`
        : "未开启批量选择";
    }
    if (selectVisibleDuplicatesButton) {
      selectVisibleDuplicatesButton.hidden = !selectionMode;
      selectVisibleDuplicatesButton.disabled = mutationInProgress || !visibleDigests.length;
      selectVisibleDuplicatesButton.textContent = allVisibleSelected
        ? "取消选择当前重复项"
        : "选择当前视图全部重复项";
    }
    if (ignoreSelectedButton) {
      ignoreSelectedButton.hidden = !selectionMode;
      ignoreSelectedButton.disabled = mutationInProgress || selectedDuplicateDigests.size === 0;
      ignoreSelectedButton.setAttribute("aria-busy", String(mutationInProgress));
    }
    document.querySelectorAll(".card[data-sha256]").forEach((card) => {
      const selected = selectionMode && selectedDuplicateDigests.has(card.dataset.sha256);
      card.classList.toggle("selection-mode", selectionMode);
      card.classList.toggle("selected", selected);
      const control = card.querySelector(".card-select");
      if (control) {
        control.hidden = !selectionMode;
        control.setAttribute("aria-pressed", String(selected));
        control.textContent = selected ? "✓" : "";
      }
    });
  }

  function setSelectionMode(enabled) {
    selectionMode = Boolean(enabled);
    if (!selectionMode) selectedDuplicateDigests.clear();
    updateSelectionUi();
  }

  function toggleVisibleDuplicateSelection() {
    const visibleDigests = getVisibleDuplicateDigests();
    const selectedSnapshot = new Set(selectedDuplicateDigests);
    const allVisibleSelected = visibleDigests.length > 0 && visibleDigests.every((digest) => selectedSnapshot.has(digest));
    visibleDigests.forEach((digest) => {
      if (allVisibleSelected) selectedDuplicateDigests.delete(digest);
      else selectedDuplicateDigests.add(digest);
    });
    updateSelectionUi();
  }

  function toggleDuplicateSelection(digest) {
    const normalized = normalizeDigest(digest);
    if (!normalized) return;
    if (selectedDuplicateDigests.has(normalized)) selectedDuplicateDigests.delete(normalized);
    else selectedDuplicateDigests.add(normalized);
    updateSelectionUi();
  }

  function renderPagination(paginationData = {}) {
    const indexed = paginationData.indexed || {};
    const pending = paginationData.pending || {};
    const indexedTotalPages = Math.max(1, Number(indexed.total_pages || 1));
    const pendingTotalPages = Math.max(1, Number(pending.total_pages || 1));
    const totalPages = Math.max(indexedTotalPages, pendingTotalPages);
    currentPage = Math.min(Math.max(1, Number(paginationData.page || currentPage)), totalPages);
    if (!pagination || !paginationPages || !paginationSummary) return;
    pagination.hidden = totalPages <= 1;
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
        currentPage = page;
        void loadWorkspace({ preserveSelection: true });
      });
      paginationPages.append(button);
      previousPage = page;
    });
    paginationSummary.textContent = `第 ${currentPage} / ${totalPages} 页 · 共 ${(Number(indexed.total || 0) + Number(pending.total || 0))} 张`;
  }

  function itemMatchesRemoval(item, { sha256s = [], locations = [] } = {}) {
    const digestSet = new Set(sha256s.map(normalizeDigest).filter(Boolean));
    const locationSet = new Set(locations.map(({ category, filename }) => `${category}\u0000${filename}`));
    return (digestSet.size > 0 && digestSet.has(normalizeDigest(item?.sha256))) ||
      locationSet.has(`${item?.category || item?.tag || ""}\u0000${item?.filename || ""}`);
  }

  function removeItemsFromWorkspace(removal) {
    if (!currentWorkspace) return;
    const indexedItemsBefore = currentWorkspace.indexed_items || [];
    const pendingItemsBefore = currentWorkspace.pending_items || [];
    const indexedItems = indexedItemsBefore.filter((item) => !itemMatchesRemoval(item, removal));
    const pendingItems = pendingItemsBefore.filter((item) => !itemMatchesRemoval(item, removal));
    const removedIndexed = indexedItemsBefore.length - indexedItems.length;
    const removedPending = pendingItemsBefore.length - pendingItems.length;
    const removedDuplicate = pendingItemsBefore.filter(
      (item) => item.duplicate && itemMatchesRemoval(item, removal),
    ).length;
    const summary = { ...(currentWorkspace.summary || {}) };
    summary.indexed = Math.max(0, Number(summary.indexed || 0) - removedIndexed);
    summary.pending = Math.max(0, Number(summary.pending || 0) - Math.max(0, removedPending - removedDuplicate));
    summary.duplicate = Math.max(0, Number(summary.duplicate || 0) - removedDuplicate);
    const removedDigests = new Set((removal.sha256s || []).map(normalizeDigest).filter(Boolean));
    currentWorkspace = {
      ...currentWorkspace,
      indexed_items: indexedItems,
      pending_items: pendingItems,
      duplicate_digests: (currentWorkspace.duplicate_digests || []).filter(
        (digest) => !removedDigests.has(normalizeDigest(digest)),
      ),
      summary,
    };
  }

  function removeCardsForItems(removal) {
    document.querySelectorAll(".card").forEach((card) => {
      const item = {
        category: card.dataset.category,
        filename: card.dataset.filename,
        sha256: card.dataset.sha256,
      };
      if (itemMatchesRemoval(item, removal)) card.remove();
    });
    for (const [target, message] of [
      [indexedItems, "暂无已完成的偷取索引"],
      [pendingItems, "当前没有待处理偷取图片"],
    ]) {
      if (!target.querySelector(".card")) renderEmpty(target, message);
    }
  }

  async function syncWorkspaceMetadata() {
    return loadWorkspace({ renderItems: false });
  }

  async function deleteIndexedItem(item, card, button) {
    const location = getImageLocation(item);
    if (!location) return;
    if (!(await requestConfirmation(
      `确认永久删除 ${location.filename}？此操作不可恢复。`,
      "永久删除图片",
    ))) return;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    mutationInProgress = true;
    updateSelectionUi();
    try {
      await apiPost("emoji/delete", {
        managed_pack_id: location.managed_pack_id,
        category: location.category,
        image_file: location.filename,
      });
      const removal = { locations: [location] };
      removeItemsFromWorkspace(removal);
      removeCardsForItems(removal);
      const refreshed = await syncWorkspaceMetadata();
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
    } finally {
      mutationInProgress = false;
      updateSelectionUi();
    }
  }

  function uniqueDuplicateDigests(items) {
    return [...new Set((items || [])
      .filter((item) => item?.duplicate && /^[0-9a-f]{64}$/i.test(String(item.sha256 || "")))
      .map((item) => String(item.sha256).toLowerCase()))];
  }

  async function ignoreDuplicateRecords(digests, button) {
    const uniqueDigests = [...new Set((digests || [])
      .map((digest) => String(digest || "").trim().toLowerCase())
      .filter((digest) => /^[0-9a-f]{64}$/.test(digest)))];
    if (!uniqueDigests.length || !packSelect.value) {
      showError(new Error("没有可忽略的重复记录"));
      return;
    }
    if (!(await requestConfirmation(
      `将忽略这张图片的全部重复记录，共 ${uniqueDigests.length} 个图片指纹；不会删除图片。`,
      "忽略重复记录",
    ))) return;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    mutationInProgress = true;
    updateSelectionUi();
    try {
      const result = await apiPost("capture/duplicates/ignore", {
        pack_id: packSelect.value,
        sha256s: uniqueDigests,
      });
      const removal = { sha256s: uniqueDigests };
      removeItemsFromWorkspace(removal);
      removeCardsForItems(removal);
      uniqueDigests.forEach((digest) => selectedDuplicateDigests.delete(digest));
      const refreshed = await syncWorkspaceMetadata();
      if (refreshed) {
        notice.textContent = result.message || "已忽略重复记录";
        notice.classList.remove("error");
      } else {
        button.disabled = false;
        button.setAttribute("aria-busy", "false");
      }
    } catch (error) {
      button.disabled = false;
      button.setAttribute("aria-busy", "false");
      showError(error);
    } finally {
      mutationInProgress = false;
      updateSelectionUi();
    }
  }

  async function ignoreSelectedDuplicates() {
    if (mutationInProgress || selectedDuplicateDigests.size === 0) return;
    await ignoreDuplicateRecords([...selectedDuplicateDigests], ignoreSelectedButton);
  }

  function renderCard(item, target) {
    const card = document.createElement("article");
    card.className = `card thumbnail-loading${item.duplicate ? " duplicate" : ""}`;
    card.dataset.category = item.category || item.tag || "";
    card.dataset.filename = item.filename || "";
    const digest = normalizeDigest(item.sha256);
    if (item.duplicate && digest) card.dataset.sha256 = digest;

    const selectionButton = document.createElement("button");
    selectionButton.type = "button";
    selectionButton.className = "card-select";
    selectionButton.hidden = true;
    selectionButton.setAttribute("aria-label", "选择重复记录");
    selectionButton.setAttribute("aria-pressed", "false");
    if (item.duplicate && digest) {
      selectionButton.addEventListener("click", (event) => {
        event.stopPropagation();
        toggleDuplicateSelection(digest);
      });
    }
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
    image.addEventListener("error", () => {
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
    meta.textContent = `${
      item.duplicate ? "重复待去重" : item.indexed ? "已索引" : "待分类"
    }`;
    const description = document.createElement("small");
    description.textContent = item.description || "点击查看图片";
    previewButton.append(thumbnail, title, tagList, meta, description);

    const actions = document.createElement("div");
    actions.className = "card-actions";
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    if (item.duplicate) {
      deleteButton.className = "card-ignore";
      deleteButton.textContent = "忽略";
      deleteButton.setAttribute("aria-label", `忽略 ${item.filename || "图片"} 的全部重复记录`);
      deleteButton.title = "忽略该图片的全部重复记录，不会删除图片";
      deleteButton.addEventListener("click", (event) => {
        event.stopPropagation();
        void ignoreDuplicateRecords([item.sha256], deleteButton);
      });
    } else {
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
    }
    actions.append(deleteButton);
    card.append(selectionButton, previewButton, actions);
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
    if (renderItems) {
      indexedItems.replaceChildren();
      pendingItems.replaceChildren();
      if (indexed.length) indexed.forEach((item) => renderCard(item, indexedItems));
      else renderEmpty(indexedItems, "暂无已完成的偷取索引");
      if (pending.length) pending.forEach((item) => renderCard(item, pendingItems));
      else renderEmpty(pendingItems, "当前没有待处理偷取图片");
    }
    renderPagination(data.pagination);

    const state = data.library_index || {};
    const indexInProgress = indexing || ["queued", "running"].includes(state.status);
    indexButton.disabled =
      indexInProgress || !state.active_pack || !(stats.pending || stats.duplicate);
    indexButton.textContent = indexInProgress ? "分类索引中……" : "分类索引待处理项";
    reindexButton.disabled = reindexing;
    const bulkDigests = selectedCategory
      ? uniqueDuplicateDigests(pending)
      : (data.duplicate_digests || []).filter((digest) => /^[0-9a-f]{64}$/i.test(String(digest)));
    ignoreDuplicatesButton.disabled = !state.active_pack || !bulkDigests.length;
    ignoreDuplicatesButton.setAttribute("aria-busy", "false");
    notice.textContent = indexing && state.status === "idle"
      ? "已提交分类索引，正在启动……"
      : state.message || "目录索引已加载";
    notice.classList.remove("error");
  }

  async function loadWorkspace({ renderItems = true, preserveSelection = false } = {}) {
    if (!packSelect.value) return;
    if (renderItems && !preserveSelection) {
      selectionMode = false;
      selectedDuplicateDigests.clear();
    }
    try {
      const params = { pack_id: packSelect.value };
      if (selectedCategory) params.category = selectedCategory;
      params.page = currentPage;
      const data = await apiGet("capture/workspace", params);
      renderWorkspace(data, { renderItems });
      if (renderItems && preserveSelection && Number(data.pagination?.page || currentPage) !== currentPage) {
        currentPage = Number(data.pagination.page);
        return loadWorkspace({ renderItems: true, preserveSelection: true });
      }
      updateSelectionUi();
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
      currentPage -= 1;
      void loadWorkspace({ preserveSelection: true });
    }
  });
  paginationNext?.addEventListener("click", () => {
    const totalPages = Math.max(
      Number(currentWorkspace?.pagination?.indexed?.total_pages || 1),
      Number(currentWorkspace?.pagination?.pending?.total_pages || 1),
    );
    if (currentPage < totalPages) {
      currentPage += 1;
      void loadWorkspace({ preserveSelection: true });
    }
  });
  selectionModeButton?.addEventListener("click", () => setSelectionMode(!selectionMode));
  selectVisibleDuplicatesButton?.addEventListener("click", () => {
    if (!mutationInProgress) toggleVisibleDuplicateSelection();
  });
  ignoreSelectedButton?.addEventListener("click", () => void ignoreSelectedDuplicates());
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
  ignoreDuplicatesButton.addEventListener("click", () => {
    if (mutationInProgress) return;
    const pending = currentWorkspace?.pending_items || [];
    const digests = selectedCategory
      ? uniqueDuplicateDigests(pending)
      : (currentWorkspace?.duplicate_digests || []);
    void ignoreDuplicateRecords(digests, ignoreDuplicatesButton);
  });
  reindexButton.addEventListener("click", async () => {
    if (!packSelect.value) return;
    if (!(await requestConfirmation(
      "将旧分类目录迁移到平铺目录，并按 meme_<哈希> 重建标签索引。继续吗？",
      "重索引表情目录",
    ))) return;
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
