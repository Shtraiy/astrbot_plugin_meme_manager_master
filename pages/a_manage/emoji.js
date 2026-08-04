window.MemeManagerUI = window.MemeManagerUI || {};
window.MemeManagerUI.emoji = window.MemeManagerUI.emoji || {};
window.MemeManagerUI.emoji.fetchEmojis = async function () {
    window.MemeManagerUI.state.loading = true;
    window.MemeManagerUI.state.error = null;
    try {
      // The image list is the primary payload. A broken description request
      // must not blank an otherwise usable catalog.
      const [emojiResult, descriptionsResult] = await Promise.allSettled([
        window.MemeManagerUI.api.apiGet("emoji"),
        window.MemeManagerUI.api.apiGet("emotions"),
      ]);
      if (emojiResult.status !== "fulfilled") {
        throw emojiResult.reason || new Error("表情包目录加载失败");
      }
      const emojiResponse =
        emojiResult.value && typeof emojiResult.value === "object" && !Array.isArray(emojiResult.value)
          ? emojiResult.value
          : {};
      const tagDescriptions =
        descriptionsResult.status === "fulfilled" &&
        descriptionsResult.value &&
        typeof descriptionsResult.value === "object" &&
        !Array.isArray(descriptionsResult.value)
          ? descriptionsResult.value
          : {};
      if (descriptionsResult.status !== "fulfilled") {
        console.warn("读取分类描述失败，继续显示表情包目录:", descriptionsResult.reason);
      }
      window.MemeManagerUI.emoji.clearDragMode();
      window.MemeManagerUI.emoji.closeBatchContextMenu();
      window.MemeManagerUI.state.latestEmojiData = emojiResponse;
      window.MemeManagerUI.state.latestTagDescriptions = tagDescriptions;
      window.MemeManagerUI.emoji.pruneSelectionState();
      window.MemeManagerUI.emoji.displayCategories(emojiResponse, tagDescriptions);
      window.MemeManagerUI.emoji.updateSidebar(emojiResponse, tagDescriptions);
      window.MemeManagerUI.emoji.updateSelectionUI();
    } catch (error) {
      window.MemeManagerUI.state.error = error?.message || String(error);
      console.error("加载表情包数据失败", error);
      window.MemeManagerUI.state.latestEmojiData = {};
      window.MemeManagerUI.state.latestTagDescriptions = {};
      window.MemeManagerUI.emoji.displayCategories({}, {});
      window.MemeManagerUI.emoji.updateSidebar({}, {});
    } finally {
      window.MemeManagerUI.state.loading = false;
    }
  }
window.MemeManagerUI.emoji.createButton = function ({
    className = "",
    text = "",
    disabled = false,
    onClick = null,
  }) {
    const button = document.createElement("button");
    button.type = "button";
    if (className) {
      button.className = className;
    }
    button.textContent = text;
    button.disabled = disabled;
    if (onClick) {
      button.addEventListener("click", onClick);
    }
    return button;
  }
window.MemeManagerUI.emoji.createIconButton = function ({
    className = "",
    iconClass = "",
    title = "",
    ariaLabel = "",
    onClick = null,
  }) {
    const button = document.createElement("button");
    button.type = "button";
    if (className) {
      button.className = className;
    }
    if (title) {
      button.title = title;
    }
    if (ariaLabel) {
      button.setAttribute("aria-label", ariaLabel);
    }

    if (iconClass) {
      const icon = document.createElement("i");
      icon.className = iconClass;
      button.appendChild(icon);
    }

    if (onClick) {
      button.addEventListener("click", onClick);
    }

    return button;
  }
window.MemeManagerUI.emoji.setButtonBusy = function (button, busyText) {
    if (!button) return;
    if (!button.dataset.originalHtml) {
      button.dataset.originalHtml = button.innerHTML;
    }
    button.disabled = true;
    button.textContent = busyText;
  }
window.MemeManagerUI.emoji.restoreButton = function (button) {
    if (!button) return;
    button.disabled = false;
    if (button.dataset.originalHtml) {
      button.innerHTML = button.dataset.originalHtml;
    }
  }
window.MemeManagerUI.emoji.getImageRequestParams = function (category, emoji, size = "preview") {
    return {
      category,
      filename: emoji,
      size,
    };
  }
window.MemeManagerUI.emoji.setEmojiPreviewLoading = function (emojiItem) {
    emojiItem.classList.remove("emoji-load-error", "emoji-loaded");
    emojiItem.classList.add("emoji-loading");
    emojiItem.setAttribute("aria-label", "正在加载表情包预览");
  }
window.MemeManagerUI.emoji.setEmojiPreviewLoaded = function (emojiItem, dataUrl) {
    emojiItem.style.backgroundImage = `url("${dataUrl}")`;
    emojiItem.dataset.previewDataUrl = dataUrl;
    emojiItem.classList.remove("emoji-loading", "emoji-load-error");
    emojiItem.classList.add("emoji-loaded");
    emojiItem.setAttribute(
      "aria-label",
      `预览表情包 ${emojiItem.dataset.emoji || ""}`,
    );
  }
window.MemeManagerUI.emoji.setEmojiPreviewError = function (emojiItem) {
    emojiItem.style.backgroundImage = "";
    emojiItem.classList.remove("emoji-loading", "emoji-loaded");
    emojiItem.classList.add("emoji-load-error");
    emojiItem.setAttribute("aria-label", "预览加载失败，点击重试");
  }
window.MemeManagerUI.emoji.loadEmojiPreview = async function (emojiItem, { force = false } = {}) {
    if (
      !emojiItem ||
      (!force &&
        (emojiItem.dataset.previewDataUrl ||
          emojiItem.dataset.loading === "true"))
    ) {
      return;
    }

    const { category, emoji } = emojiItem.dataset;
    if (!category || !emoji) {
      window.MemeManagerUI.emoji.setEmojiPreviewError(emojiItem);
      return;
    }

    emojiItem.dataset.loading = "true";
    window.MemeManagerUI.emoji.setEmojiPreviewLoading(emojiItem);
    try {
      const data = await window.MemeManagerUI.api.apiGet(
        "meme_image_data",
        window.MemeManagerUI.emoji.getImageRequestParams(category, emoji, "preview"),
      );
      if (!data?.data_url) {
        throw new Error("图片接口未返回预览数据");
      }
      window.MemeManagerUI.emoji.setEmojiPreviewLoaded(emojiItem, data.data_url);
    } catch (error) {
      console.error("加载表情包预览失败:", error);
      window.MemeManagerUI.emoji.setEmojiPreviewError(emojiItem);
    } finally {
      emojiItem.dataset.loading = "false";
    }
  }
window.MemeManagerUI.emoji.retryEmojiPreview = function (emojiItem) {
    if (!emojiItem) {
      return;
    }
    delete emojiItem.dataset.previewDataUrl;
    void window.MemeManagerUI.emoji.loadEmojiPreview(emojiItem, { force: true });
  }
window.MemeManagerUI.emoji.loadPreviewImage = async function (category, emoji, size = "preview") {
    const data = await window.MemeManagerUI.api.apiGet(
      "meme_image_data",
      window.MemeManagerUI.emoji.getImageRequestParams(category, emoji, size),
    );
    if (!data?.data_url) {
      throw new Error("图片接口未返回预览数据");
    }
    return data.data_url;
  }
window.MemeManagerUI.emoji.setImagePreviewBusy = function (isBusy) {
    if (window.MemeManagerUI.state.imagePreviewLoading) {
      window.MemeManagerUI.state.imagePreviewLoading.classList.toggle("hidden", !isBusy);
    }
    if (window.MemeManagerUI.state.imagePreviewOriginalBtn) {
      window.MemeManagerUI.state.imagePreviewOriginalBtn.disabled = isBusy;
    }
  }
window.MemeManagerUI.emoji.closeImagePreview = function () {
    window.MemeManagerUI.state.imagePreviewState = null;
    if (window.MemeManagerUI.state.imagePreviewModalRoot) {
      window.MemeManagerUI.state.imagePreviewModalRoot.classList.add("hidden");
      window.MemeManagerUI.state.imagePreviewModalRoot.setAttribute("aria-hidden", "true");
    }
    if (window.MemeManagerUI.state.imagePreviewImg) {
      window.MemeManagerUI.state.imagePreviewImg.removeAttribute("src");
    }
    window.MemeManagerUI.emoji.setImagePreviewBusy(false);
  }
window.MemeManagerUI.emoji.openImagePreview = async function (category, emoji, previewDataUrl = "") {
    if (!window.MemeManagerUI.state.imagePreviewModalRoot || !window.MemeManagerUI.state.imagePreviewImg) {
      return;
    }

    const previewState = {
      category,
      emoji,
      packId: String(window.MemeManagerUI.state.activeManagePackId || window.MemeManagerUI.state.managePackSelect?.value || ""),
    };
    window.MemeManagerUI.state.imagePreviewState = previewState;
    window.MemeManagerUI.state.imagePreviewModalRoot.classList.remove("hidden");
    window.MemeManagerUI.state.imagePreviewModalRoot.setAttribute("aria-hidden", "false");
    window.MemeManagerUI.state.imagePreviewImg.alt = `表情包预览：${emoji}`;
    if (previewDataUrl) {
      window.MemeManagerUI.state.imagePreviewImg.src = previewDataUrl;
    } else {
      window.MemeManagerUI.state.imagePreviewImg.removeAttribute("src");
    }

    window.MemeManagerUI.emoji.setImagePreviewBusy(!previewDataUrl);
    const previewRequest = previewDataUrl
      ? Promise.resolve(previewDataUrl)
      : window.MemeManagerUI.emoji.loadPreviewImage(category, emoji, "preview");
    const [previewResult] = await Promise.allSettled([previewRequest]);
    if (window.MemeManagerUI.state.imagePreviewState !== previewState) {
      return;
    }
    if (previewResult.status === "rejected") {
      const error = previewResult.reason;
      console.error("打开大图预览失败:", error);
      window.MemeManagerUI.emoji.closeImagePreview();
      window.MemeManagerUI.dialogs.showToast("图片预览加载失败，请稍后重试。", "error", "加载失败");
      return;
    }
    window.MemeManagerUI.state.imagePreviewImg.src = previewResult.value;
    window.MemeManagerUI.emoji.setImagePreviewBusy(false);

    window.MemeManagerUI.state.imagePreviewCloseBtn?.focus();
  }
window.MemeManagerUI.emoji.showOriginalPreview = async function () {
    if (!window.MemeManagerUI.state.imagePreviewState || !window.MemeManagerUI.state.imagePreviewImg) {
      return;
    }

    const previewState = window.MemeManagerUI.state.imagePreviewState;
    window.MemeManagerUI.emoji.setImagePreviewBusy(true);
    try {
      const originalDataUrl = await window.MemeManagerUI.emoji.loadPreviewImage(
        previewState.category,
        previewState.emoji,
        "original",
      );
      if (window.MemeManagerUI.state.imagePreviewState === previewState) {
        window.MemeManagerUI.state.imagePreviewImg.src = originalDataUrl;
      }
    } catch (error) {
      console.error("加载原图失败:", error);
      window.MemeManagerUI.dialogs.showToast("原图加载失败，可能文件过大或已不存在。", "error", "加载失败");
    } finally {
      if (window.MemeManagerUI.state.imagePreviewState === previewState) {
        window.MemeManagerUI.emoji.setImagePreviewBusy(false);
      }
    }
  }
window.MemeManagerUI.emoji.refreshUi = async function ({
    emojis = false,
    syncStatus = false,
  } = {}) {
    if (emojis) {
      await Promise.all([window.MemeManagerUI.emoji.fetchEmojis(), window.MemeManagerUI.pack.refreshManagePackSummaries()]);
    }
    if (syncStatus) {
      await window.MemeManagerUI.pack.checkSyncStatus(false);
    }
  }
window.MemeManagerUI.emoji.isCompactViewport = function () {
    return window.matchMedia(window.MemeManagerUI.state.MOBILE_LAYOUT_MEDIA).matches;
  }
window.MemeManagerUI.emoji.isConsoleVisible = function () {
    return window.MemeManagerUI.emoji.isCompactViewport()
      ? document.body.classList.contains("panel-console-open")
      : !document.body.classList.contains("panel-console-hidden");
  }
window.MemeManagerUI.emoji.isDirectoryVisible = function () {
    return window.MemeManagerUI.emoji.isCompactViewport()
      ? document.body.classList.contains("panel-directory-open")
      : !document.body.classList.contains("panel-directory-hidden");
  }
window.MemeManagerUI.emoji.setConsoleVisible = function (visible) {
    if (window.MemeManagerUI.emoji.isCompactViewport()) {
      document.body.classList.toggle("panel-console-open", visible);
      return;
    }
    document.body.classList.toggle("panel-console-hidden", !visible);
  }
window.MemeManagerUI.emoji.setDirectoryVisible = function (visible) {
    if (window.MemeManagerUI.emoji.isCompactViewport()) {
      document.body.classList.toggle("panel-directory-open", visible);
      return;
    }
    document.body.classList.toggle("panel-directory-hidden", !visible);
  }
window.MemeManagerUI.emoji.closeAllPanels = function () {
    window.MemeManagerUI.emoji.setConsoleVisible(false);
    window.MemeManagerUI.emoji.setDirectoryVisible(false);
  }
window.MemeManagerUI.emoji.updatePanelToggleState = function () {
    const consoleVisible = window.MemeManagerUI.emoji.isConsoleVisible();
    const directoryVisible = window.MemeManagerUI.emoji.isDirectoryVisible();

    if (window.MemeManagerUI.state.consoleToggleBtn) {
      window.MemeManagerUI.state.consoleToggleBtn.setAttribute("aria-expanded", String(consoleVisible));
      window.MemeManagerUI.state.consoleToggleBtn.setAttribute(
        "aria-label",
        consoleVisible ? "收起控制台" : "展开控制台",
      );
      window.MemeManagerUI.state.consoleToggleBtn.classList.toggle("active", consoleVisible);
    }

    if (window.MemeManagerUI.state.directoryToggleBtn) {
      window.MemeManagerUI.state.directoryToggleBtn.setAttribute(
        "aria-expanded",
        String(directoryVisible),
      );
      window.MemeManagerUI.state.directoryToggleBtn.setAttribute(
        "aria-label",
        directoryVisible ? "收起目录" : "展开目录",
      );
      window.MemeManagerUI.state.directoryToggleBtn.classList.toggle("active", directoryVisible);
    }

    if (window.MemeManagerUI.state.sidebarBackdrop) {
      const showBackdrop =
        window.MemeManagerUI.emoji.isCompactViewport() && (consoleVisible || directoryVisible);
      window.MemeManagerUI.state.sidebarBackdrop.classList.toggle("hidden", !showBackdrop);
      window.MemeManagerUI.state.sidebarBackdrop.setAttribute("aria-hidden", String(!showBackdrop));
    }

    window.MemeManagerUI.state.leftPanel?.setAttribute("aria-hidden", String(!consoleVisible));
    window.MemeManagerUI.state.directoryPanel?.setAttribute("aria-hidden", String(!directoryVisible));
  }
window.MemeManagerUI.emoji.syncSidebarLayout = function () {
    if (window.MemeManagerUI.emoji.isCompactViewport()) {
      document.body.classList.remove("panel-console-hidden");
      document.body.classList.remove("panel-directory-hidden");
      window.MemeManagerUI.emoji.closeAllPanels();
      window.MemeManagerUI.emoji.updatePanelToggleState();
      return;
    }

    document.body.classList.remove(
      "panel-console-open",
      "panel-directory-open",
    );
    if (
      !document.body.classList.contains("panel-console-hidden") &&
      !document.body.classList.contains("panel-directory-hidden")
    ) {
      window.MemeManagerUI.emoji.setConsoleVisible(true);
      window.MemeManagerUI.emoji.setDirectoryVisible(true);
    }
    window.MemeManagerUI.emoji.updatePanelToggleState();
  }
window.MemeManagerUI.emoji.toggleConsolePanel = function () {
    window.MemeManagerUI.emoji.setConsoleVisible(!window.MemeManagerUI.emoji.isConsoleVisible());
    window.MemeManagerUI.emoji.updatePanelToggleState();
  }
window.MemeManagerUI.emoji.toggleDirectoryPanel = function () {
    window.MemeManagerUI.emoji.setDirectoryVisible(!window.MemeManagerUI.emoji.isDirectoryVisible());
    window.MemeManagerUI.emoji.updatePanelToggleState();
  }
window.MemeManagerUI.emoji.formatBytes = function (bytes) {
    if (typeof bytes !== "number" || Number.isNaN(bytes) || bytes < 0) {
      return "未知";
    }
    if (bytes === 0) {
      return "0 B";
    }

    const units = ["B", "KB", "MB", "GB", "TB"];
    let value = bytes;
    let unitIndex = 0;

    while (value >= 1024 && unitIndex < units.length - 1) {
      value /= 1024;
      unitIndex += 1;
    }

    const precision = unitIndex === 0 ? 0 : value >= 100 ? 0 : 1;
    return `${value.toFixed(precision)} ${units[unitIndex]}`;
  }
window.MemeManagerUI.emoji.getSortedCategories = function () {
    return Object.keys(window.MemeManagerUI.state.latestEmojiData).sort((left, right) =>
      left.localeCompare(right, "zh-CN"),
    );
  }
window.MemeManagerUI.emoji.getMoveableCountForTarget = function (items, targetCategory) {
    if (!targetCategory) {
      return 0;
    }

    return window.MemeManagerUI.emoji.dedupeEmojiItems(items).filter(
      (item) => item.category !== targetCategory,
    ).length;
  }
window.MemeManagerUI.emoji.getAvailableMoveTargets = function (
    items = Array.from(window.MemeManagerUI.state.selectionState.items.values()),
  ) {
    const uniqueItems = window.MemeManagerUI.emoji.dedupeEmojiItems(items);
    if (uniqueItems.length === 0) {
      return [];
    }

    return window.MemeManagerUI.emoji.getSortedCategories().filter(
      (category) => window.MemeManagerUI.emoji.getMoveableCountForTarget(uniqueItems, category) > 0,
    );
  }
window.MemeManagerUI.emoji.dedupeEmojiItems = function (items) {
    const uniqueItems = new Map();
    (items || []).forEach((item) => {
      if (!item?.category || !item?.emoji) {
        return;
      }
      uniqueItems.set(window.MemeManagerUI.emoji.createSelectionKey(item.category, item.emoji), {
        category: item.category,
        emoji: item.emoji,
      });
    });
    return Array.from(uniqueItems.values());
  }
window.MemeManagerUI.emoji.groupEmojiItemsByCategory = function (items) {
    const groupedItems = new Map();
    window.MemeManagerUI.emoji.dedupeEmojiItems(items).forEach((item) => {
      if (!groupedItems.has(item.category)) {
        groupedItems.set(item.category, []);
      }
      groupedItems.get(item.category).push(item.emoji);
    });
    return groupedItems;
  }
window.MemeManagerUI.emoji.setClipboardItems = function (items) {
    window.MemeManagerUI.state.clipboardState.items = window.MemeManagerUI.emoji.dedupeEmojiItems(items);
  }
window.MemeManagerUI.emoji.getClipboardItems = function () {
    return window.MemeManagerUI.emoji.dedupeEmojiItems(window.MemeManagerUI.state.clipboardState.items);
  }
window.MemeManagerUI.emoji.getContextMenuTargetItems = function (targetEmojiItem) {
    if (!targetEmojiItem) {
      return window.MemeManagerUI.emoji.dedupeEmojiItems(Array.from(window.MemeManagerUI.state.selectionState.items.values()));
    }

    const targetCategory = targetEmojiItem.dataset.category;
    const targetEmoji = targetEmojiItem.dataset.emoji;
    if (
      window.MemeManagerUI.state.selectionState.enabled &&
      window.MemeManagerUI.emoji.isEmojiSelected(targetCategory, targetEmoji)
    ) {
      return window.MemeManagerUI.emoji.dedupeEmojiItems(Array.from(window.MemeManagerUI.state.selectionState.items.values()));
    }

    return [{ category: targetCategory, emoji: targetEmoji }];
  }
window.MemeManagerUI.emoji.getPasteableClipboardItems = function (targetCategory) {
    if (!targetCategory) {
      return [];
    }

    return window.MemeManagerUI.emoji.getClipboardItems().filter(
      (item) => item.category !== targetCategory,
    );
  }
window.MemeManagerUI.emoji.closeBatchContextMenu = function () {
    window.MemeManagerUI.state.contextMenuState.items = [];
    window.MemeManagerUI.state.contextMenuState.targetCategory = null;
    if (window.MemeManagerUI.state.batchContextMenu) {
      window.MemeManagerUI.state.batchContextMenu.classList.add("hidden");
      window.MemeManagerUI.state.batchContextMenu.setAttribute("aria-hidden", "true");
      window.MemeManagerUI.state.batchContextMenu.style.left = "-9999px";
      window.MemeManagerUI.state.batchContextMenu.style.top = "-9999px";
    }
  }
window.MemeManagerUI.emoji.openBatchContextMenu = function (event) {
    if (!window.MemeManagerUI.state.batchContextMenu || !window.MemeManagerUI.state.selectionState.enabled) {
      return;
    }

    window.MemeManagerUI.emoji.closeBatchContextMenu();

    const targetEmojiItem = event.target.closest(".emoji-item");
    const targetCategoryElement = event.target.closest(".category");
    const targetCategory =
      targetEmojiItem?.dataset.category ||
      targetCategoryElement?.dataset.category ||
      null;
    const targetItems = window.MemeManagerUI.emoji.getContextMenuTargetItems(targetEmojiItem);
    const pasteableItems = window.MemeManagerUI.emoji.getPasteableClipboardItems(targetCategory);

    if (targetItems.length === 0 && pasteableItems.length === 0) {
      return;
    }

    window.MemeManagerUI.state.contextMenuState.items = targetItems;
    window.MemeManagerUI.state.contextMenuState.targetCategory = targetCategory;

    if (window.MemeManagerUI.state.batchContextMenuTitle) {
      window.MemeManagerUI.state.batchContextMenuTitle.textContent =
        targetItems.length > 0
          ? `批量管理 ${targetItems.length} 个文件`
          : "批量管理";
    }
    if (window.MemeManagerUI.state.batchContextMenuSubtitle) {
      if (targetCategory && pasteableItems.length > 0) {
        window.MemeManagerUI.state.batchContextMenuSubtitle.textContent = `当前分类：${targetCategory}，可粘贴 ${pasteableItems.length} 个文件`;
      } else if (targetCategory) {
        window.MemeManagerUI.state.batchContextMenuSubtitle.textContent = `当前分类：${targetCategory}`;
      } else {
        window.MemeManagerUI.state.batchContextMenuSubtitle.textContent = "选择一个操作继续";
      }
    }

    if (window.MemeManagerUI.state.contextMenuDeleteBtn) {
      window.MemeManagerUI.state.contextMenuDeleteBtn.disabled = targetItems.length === 0;
    }
    if (window.MemeManagerUI.state.contextMenuMoveBtn) {
      window.MemeManagerUI.state.contextMenuMoveBtn.disabled =
        targetItems.length === 0 ||
        window.MemeManagerUI.emoji.getAvailableMoveTargets(targetItems).length === 0;
    }
    if (window.MemeManagerUI.state.contextMenuCopyBtn) {
      window.MemeManagerUI.state.contextMenuCopyBtn.disabled = targetItems.length === 0;
    }
    if (window.MemeManagerUI.state.contextMenuPasteBtn) {
      window.MemeManagerUI.state.contextMenuPasteBtn.disabled =
        pasteableItems.length === 0 || !targetCategory;
    }

    window.MemeManagerUI.state.batchContextMenu.classList.remove("hidden");
    window.MemeManagerUI.state.batchContextMenu.setAttribute("aria-hidden", "false");

    requestAnimationFrame(() => {
      const menuWidth = window.MemeManagerUI.state.batchContextMenu.offsetWidth || 240;
      const menuHeight = window.MemeManagerUI.state.batchContextMenu.offsetHeight || 220;
      const left = Math.min(
        window.innerWidth - menuWidth - 12,
        Math.max(12, event.clientX),
      );
      const top = Math.min(
        window.innerHeight - menuHeight - 12,
        Math.max(12, event.clientY),
      );
      window.MemeManagerUI.state.batchContextMenu.style.left = `${left}px`;
      window.MemeManagerUI.state.batchContextMenu.style.top = `${top}px`;
    });
  }
window.MemeManagerUI.emoji.shouldOpenBatchContextMenu = function (event) {
    if (!window.MemeManagerUI.state.selectionState.enabled || window.MemeManagerUI.emoji.hasActiveDragInteraction()) {
      return false;
    }

    return Boolean(
      event.target.closest(".emoji-item") ||
      event.target.closest(".emoji-upload") ||
      event.target.closest(".category"),
    );
  }
window.MemeManagerUI.emoji.getDragItemsForEmoji = function (category, emoji) {
    if (window.MemeManagerUI.state.selectionState.enabled && window.MemeManagerUI.emoji.isEmojiSelected(category, emoji)) {
      return window.MemeManagerUI.emoji.dedupeEmojiItems(Array.from(window.MemeManagerUI.state.selectionState.items.values()));
    }
    return [{ category, emoji }];
  }
window.MemeManagerUI.emoji.getDragReadyLabel = function (itemCount) {
    return itemCount > 1 ? `${itemCount}项` : "拖";
  }
window.MemeManagerUI.emoji.hasActiveDragInteraction = function () {
    return Boolean(
      window.MemeManagerUI.state.longPressState.emojiItem ||
      window.MemeManagerUI.state.dragModeState.pointerId !== null ||
      window.MemeManagerUI.state.dragModeState.items.length > 0,
    );
  }
window.MemeManagerUI.emoji.syncInteractionGuardState = function () {
    document.body.classList.toggle(
      "drag-session-active",
      window.MemeManagerUI.emoji.hasActiveDragInteraction(),
    );
  }
window.MemeManagerUI.emoji.updateDragHudPosition = function (clientX, clientY) {
    if (!window.MemeManagerUI.state.dragHud) {
      return;
    }

    const hudRect = window.MemeManagerUI.state.dragHud.getBoundingClientRect();
    const hudWidth = hudRect.width || 72;
    const hudHeight = hudRect.height || 72;
    const x = Math.min(
      window.innerWidth - hudWidth - 10,
      Math.max(10, clientX + window.MemeManagerUI.state.DRAG_HUD_OFFSET_X),
    );
    const y = Math.min(
      window.innerHeight - hudHeight - 10,
      Math.max(10, clientY - window.MemeManagerUI.state.DRAG_HUD_OFFSET_Y),
    );

    window.MemeManagerUI.state.dragHud.style.transform = `translate3d(${Math.round(x)}px, ${Math.round(y)}px, 0)`;
  }
window.MemeManagerUI.emoji.stopDragAutoScroll = function () {
    if (window.MemeManagerUI.state.dragModeState.autoScrollFrameId) {
      cancelAnimationFrame(window.MemeManagerUI.state.dragModeState.autoScrollFrameId);
      window.MemeManagerUI.state.dragModeState.autoScrollFrameId = null;
    }
  }
window.MemeManagerUI.emoji.stepDragAutoScroll = function () {
    if (window.MemeManagerUI.state.dragModeState.pointerId === null) {
      window.MemeManagerUI.emoji.stopDragAutoScroll();
      return;
    }

    const topThreshold = 96;
    const bottomThreshold = window.innerHeight - 96;
    let deltaY = 0;

    if (window.MemeManagerUI.state.dragModeState.lastClientY < topThreshold) {
      deltaY = Math.max(-18, (window.MemeManagerUI.state.dragModeState.lastClientY - topThreshold) * 0.18);
    } else if (window.MemeManagerUI.state.dragModeState.lastClientY > bottomThreshold) {
      deltaY = Math.min(
        18,
        (window.MemeManagerUI.state.dragModeState.lastClientY - bottomThreshold) * 0.18,
      );
    }

    if (deltaY !== 0) {
      window.scrollBy({ top: deltaY, behavior: "auto" });
      window.MemeManagerUI.emoji.updateActiveDropTarget(
        window.MemeManagerUI.state.dragModeState.lastClientX,
        window.MemeManagerUI.state.dragModeState.lastClientY,
      );
      window.MemeManagerUI.emoji.showDragHud({
        label: window.MemeManagerUI.emoji.getDragReadyLabel(window.MemeManagerUI.state.dragModeState.items.length),
        caption: window.MemeManagerUI.state.dragModeState.activeCategory
          ? `松手后移动到 ${window.MemeManagerUI.state.dragModeState.activeCategory}`
          : "拖到屏幕边缘可自动滚动",
        progress: 1,
        clientX: window.MemeManagerUI.state.dragModeState.lastClientX,
        clientY: window.MemeManagerUI.state.dragModeState.lastClientY,
        state: window.MemeManagerUI.state.dragModeState.activeCategory ? "target" : "ready",
      });
    }

    window.MemeManagerUI.state.dragModeState.autoScrollFrameId = requestAnimationFrame(stepDragAutoScroll);
  }
window.MemeManagerUI.emoji.ensureDragAutoScroll = function () {
    if (window.MemeManagerUI.state.dragModeState.autoScrollFrameId) {
      return;
    }
    window.MemeManagerUI.state.dragModeState.autoScrollFrameId = requestAnimationFrame(window.MemeManagerUI.emoji.stepDragAutoScroll);
  }
window.MemeManagerUI.emoji.showDragHud = function ({
    label,
    caption,
    progress = 0,
    clientX = null,
    clientY = null,
    state = "press",
  }) {
    if (!window.MemeManagerUI.state.dragHud) {
      return;
    }

    const safeProgress = Math.max(0, Math.min(progress, 1));
    window.MemeManagerUI.state.dragHud.classList.remove("hidden");
    window.MemeManagerUI.state.dragHud.classList.add("visible");
    window.MemeManagerUI.state.dragHud.dataset.state = state;
    window.MemeManagerUI.state.dragHud.style.setProperty(
      "--drag-hud-progress",
      `${safeProgress * 360}deg`,
    );
    window.MemeManagerUI.state.dragHud.setAttribute("aria-hidden", "false");

    if (window.MemeManagerUI.state.dragHudLabel) {
      window.MemeManagerUI.state.dragHudLabel.textContent = label;
    }
    if (window.MemeManagerUI.state.dragHudCaption) {
      window.MemeManagerUI.state.dragHudCaption.textContent = caption;
    }
    if (typeof clientX === "number" && typeof clientY === "number") {
      window.MemeManagerUI.emoji.updateDragHudPosition(clientX, clientY);
    }
  }
window.MemeManagerUI.emoji.hideDragHud = function () {
    if (!window.MemeManagerUI.state.dragHud) {
      return;
    }

    window.MemeManagerUI.state.dragHud.classList.remove("visible");
    window.MemeManagerUI.state.dragHud.classList.add("hidden");
    window.MemeManagerUI.state.dragHud.dataset.state = "idle";
    window.MemeManagerUI.state.dragHud.style.setProperty("--drag-hud-progress", "0deg");
    window.MemeManagerUI.state.dragHud.style.transform = "translate3d(-9999px, -9999px, 0)";
    window.MemeManagerUI.state.dragHud.setAttribute("aria-hidden", "true");

    if (window.MemeManagerUI.state.dragHudLabel) {
      window.MemeManagerUI.state.dragHudLabel.textContent = `${Math.ceil(window.MemeManagerUI.state.LONG_PRESS_DURATION_MS / 1000)}s`;
    }
    if (window.MemeManagerUI.state.dragHudCaption) {
      window.MemeManagerUI.state.dragHudCaption.textContent = `长按 ${Math.ceil(window.MemeManagerUI.state.LONG_PRESS_DURATION_MS / 1000)} 秒进入拖拽`;
    }
  }
window.MemeManagerUI.emoji.setLongPressProgress = function (progress, label) {
    if (!window.MemeManagerUI.state.longPressState.emojiItem) {
      return;
    }

    window.MemeManagerUI.emoji.showDragHud({
      label,
      caption: `长按 ${Math.ceil(window.MemeManagerUI.state.LONG_PRESS_DURATION_MS / 1000)} 秒进入拖拽`,
      progress,
      clientX: window.MemeManagerUI.state.longPressState.currentX,
      clientY: window.MemeManagerUI.state.longPressState.currentY,
      state: "press",
    });
  }
window.MemeManagerUI.emoji.resetLongPressVisual = function (emojiItem) {
    if (!emojiItem) {
      return;
    }

    emojiItem.classList.remove("long-press-active");
  }
window.MemeManagerUI.emoji.cancelLongPress = function ({ preserveReady = false, keepHud = false } = {}) {
    if (window.MemeManagerUI.state.longPressState.timeoutId) {
      clearTimeout(window.MemeManagerUI.state.longPressState.timeoutId);
      window.MemeManagerUI.state.longPressState.timeoutId = null;
    }
    if (window.MemeManagerUI.state.longPressState.intervalId) {
      clearInterval(window.MemeManagerUI.state.longPressState.intervalId);
      window.MemeManagerUI.state.longPressState.intervalId = null;
    }
    if (window.MemeManagerUI.state.longPressState.emojiItem) {
      window.MemeManagerUI.state.longPressState.emojiItem.classList.remove("long-press-active");
      if (!preserveReady) {
        window.MemeManagerUI.emoji.resetLongPressVisual(window.MemeManagerUI.state.longPressState.emojiItem);
      }
    }

    window.MemeManagerUI.state.longPressState.emojiItem = null;
    window.MemeManagerUI.state.longPressState.pointerId = null;
    window.MemeManagerUI.state.longPressState.startTime = 0;
    window.MemeManagerUI.state.longPressState.startX = 0;
    window.MemeManagerUI.state.longPressState.startY = 0;
    window.MemeManagerUI.state.longPressState.currentX = 0;
    window.MemeManagerUI.state.longPressState.currentY = 0;

    if (!keepHud && window.MemeManagerUI.state.dragModeState.pointerId === null) {
      window.MemeManagerUI.emoji.hideDragHud();
    }

    window.MemeManagerUI.emoji.syncInteractionGuardState();
  }
window.MemeManagerUI.emoji.updateActiveDropTarget = function (clientX, clientY) {
    window.MemeManagerUI.emoji.clearCategoryDropHighlights();
    window.MemeManagerUI.state.dragModeState.activeCategory = null;

    const hoveredElement = document.elementFromPoint(clientX, clientY);
    const categoryDiv = hoveredElement?.closest(".category");
    const targetCategory = categoryDiv?.dataset?.category;

    if (!categoryDiv || !targetCategory) {
      return;
    }

    if (!window.MemeManagerUI.emoji.hasMoveableItemsForTarget(window.MemeManagerUI.state.dragModeState.items, targetCategory)) {
      return;
    }

    window.MemeManagerUI.state.dragModeState.activeCategory = targetCategory;
    categoryDiv.classList.add("category-drop-active");
  }
window.MemeManagerUI.emoji.startPointerDrag = function (event) {
    if (window.MemeManagerUI.state.dragModeState.items.length === 0) {
      return;
    }

    window.MemeManagerUI.state.dragModeState.pointerId = event.pointerId;
    window.MemeManagerUI.state.dragModeState.isPointerDragging = false;
    window.MemeManagerUI.state.dragModeState.activeCategory = null;
    window.MemeManagerUI.state.dragModeState.captureElement = event.currentTarget;
    window.MemeManagerUI.state.dragModeState.lastClientX = event.clientX;
    window.MemeManagerUI.state.dragModeState.lastClientY = event.clientY;
    window.MemeManagerUI.emoji.updateActiveDropTarget(event.clientX, event.clientY);
    window.MemeManagerUI.emoji.ensureDragAutoScroll();
    window.MemeManagerUI.emoji.showDragHud({
      label: window.MemeManagerUI.emoji.getDragReadyLabel(window.MemeManagerUI.state.dragModeState.items.length),
      caption: "拖到目标分类，松手即可移动",
      progress: 1,
      clientX: event.clientX,
      clientY: event.clientY,
      state: "ready",
    });
  }
window.MemeManagerUI.emoji.updatePointerDrag = function (event) {
    if (
      window.MemeManagerUI.state.dragModeState.pointerId === null ||
      window.MemeManagerUI.state.dragModeState.pointerId !== event.pointerId ||
      window.MemeManagerUI.state.dragModeState.items.length === 0
    ) {
      return;
    }

    window.MemeManagerUI.state.dragModeState.isPointerDragging = true;
    window.MemeManagerUI.state.dragModeState.lastClientX = event.clientX;
    window.MemeManagerUI.state.dragModeState.lastClientY = event.clientY;
    window.MemeManagerUI.emoji.updateActiveDropTarget(event.clientX, event.clientY);
    window.MemeManagerUI.emoji.showDragHud({
      label: window.MemeManagerUI.emoji.getDragReadyLabel(window.MemeManagerUI.state.dragModeState.items.length),
      caption: window.MemeManagerUI.state.dragModeState.activeCategory
        ? `松手后移动到 ${window.MemeManagerUI.state.dragModeState.activeCategory}`
        : "拖到目标分类，松手即可移动",
      progress: 1,
      clientX: event.clientX,
      clientY: event.clientY,
      state: window.MemeManagerUI.state.dragModeState.activeCategory ? "target" : "ready",
    });
  }
window.MemeManagerUI.emoji.finishPointerDrag = async function (event) {
    if (
      window.MemeManagerUI.state.dragModeState.pointerId === null ||
      window.MemeManagerUI.state.dragModeState.pointerId !== event.pointerId
    ) {
      return;
    }

    const targetCategory = window.MemeManagerUI.state.dragModeState.activeCategory;
    const dragItems = window.MemeManagerUI.emoji.dedupeEmojiItems(window.MemeManagerUI.state.dragModeState.items);
    const wasDragging = window.MemeManagerUI.state.dragModeState.isPointerDragging;

    window.MemeManagerUI.state.dragModeState.pointerId = null;
    window.MemeManagerUI.state.dragModeState.activeCategory = null;
    window.MemeManagerUI.state.dragModeState.isPointerDragging = false;
    window.MemeManagerUI.state.dragModeState.lastClientX = 0;
    window.MemeManagerUI.state.dragModeState.lastClientY = 0;
    window.MemeManagerUI.emoji.stopDragAutoScroll();
    if (
      window.MemeManagerUI.state.dragModeState.captureElement &&
      typeof event.pointerId === "number" &&
      typeof window.MemeManagerUI.state.dragModeState.captureElement.releasePointerCapture === "function"
    ) {
      try {
        window.MemeManagerUI.state.dragModeState.captureElement.releasePointerCapture(event.pointerId);
      } catch {}
    }
    window.MemeManagerUI.state.dragModeState.captureElement = null;
    window.MemeManagerUI.emoji.clearCategoryDropHighlights();
    window.MemeManagerUI.emoji.hideDragHud();
    window.MemeManagerUI.emoji.syncInteractionGuardState();

    if (
      targetCategory &&
      window.MemeManagerUI.emoji.hasMoveableItemsForTarget(dragItems, targetCategory)
    ) {
      await window.MemeManagerUI.emoji.moveEmojiItemsToCategory(targetCategory, dragItems);
      return;
    }

    if (wasDragging) {
      window.MemeManagerUI.emoji.clearDragMode();
      window.MemeManagerUI.dialogs.showToast("未拖到有效分类，已取消本次移动。", "warning", "拖拽未完成");
      return;
    }

    if (event.pointerType !== "mouse" && dragItems.length > 0) {
      window.MemeManagerUI.dialogs.showToast(
        "拖拽模式已开启，继续拖到目标分类即可移动。",
        "info",
        "等待拖拽",
      );
    }
  }
window.MemeManagerUI.emoji.clearDragMode = function () {
    window.MemeManagerUI.emoji.cancelLongPress({ keepHud: true });

    if (window.MemeManagerUI.state.dragModeState.timeoutId) {
      clearTimeout(window.MemeManagerUI.state.dragModeState.timeoutId);
      window.MemeManagerUI.state.dragModeState.timeoutId = null;
    }

    window.MemeManagerUI.emoji.stopDragAutoScroll();
    if (
      window.MemeManagerUI.state.dragModeState.captureElement &&
      typeof window.MemeManagerUI.state.dragModeState.pointerId === "number" &&
      typeof window.MemeManagerUI.state.dragModeState.captureElement.releasePointerCapture === "function"
    ) {
      try {
        window.MemeManagerUI.state.dragModeState.captureElement.releasePointerCapture(
          window.MemeManagerUI.state.dragModeState.pointerId,
        );
      } catch {}
    }

    window.MemeManagerUI.state.dragModeState.items = [];
    window.MemeManagerUI.state.dragModeState.pointerId = null;
    window.MemeManagerUI.state.dragModeState.activeCategory = null;
    window.MemeManagerUI.state.dragModeState.isPointerDragging = false;
    window.MemeManagerUI.state.dragModeState.captureElement = null;
    window.MemeManagerUI.state.dragModeState.lastClientX = 0;
    window.MemeManagerUI.state.dragModeState.lastClientY = 0;
    document.querySelectorAll(".emoji-item").forEach((emojiItem) => {
      emojiItem.classList.remove("drag-ready", "dragging");
      window.MemeManagerUI.emoji.resetLongPressVisual(emojiItem);
    });
    window.MemeManagerUI.emoji.clearCategoryDropHighlights();
    window.MemeManagerUI.emoji.hideDragHud();
    window.MemeManagerUI.emoji.syncInteractionGuardState();
  }
window.MemeManagerUI.emoji.armDragMode = function (items, pointerContext = {}) {
    const dragItems = window.MemeManagerUI.emoji.dedupeEmojiItems(items);
    if (dragItems.length === 0) {
      return;
    }

    window.MemeManagerUI.emoji.clearDragMode();
    window.MemeManagerUI.state.dragModeState.items = dragItems;
    const armedKeys = new Set(
      dragItems.map(({ category, emoji }) =>
        window.MemeManagerUI.emoji.createSelectionKey(category, emoji),
      ),
    );

    document.querySelectorAll(".emoji-item").forEach((emojiItem) => {
      const emojiKey = window.MemeManagerUI.emoji.createSelectionKey(
        emojiItem.dataset.category,
        emojiItem.dataset.emoji,
      );
      const armed = armedKeys.has(emojiKey);
      emojiItem.classList.toggle("drag-ready", armed);
      window.MemeManagerUI.emoji.resetLongPressVisual(emojiItem);
    });

    if (
      typeof pointerContext.clientX === "number" &&
      typeof pointerContext.clientY === "number"
    ) {
      window.MemeManagerUI.state.dragModeState.pointerId =
        typeof pointerContext.pointerId === "number"
          ? pointerContext.pointerId
          : null;
      window.MemeManagerUI.state.dragModeState.captureElement = pointerContext.sourceElement || null;
      window.MemeManagerUI.state.dragModeState.lastClientX = pointerContext.clientX;
      window.MemeManagerUI.state.dragModeState.lastClientY = pointerContext.clientY;
      if (
        window.MemeManagerUI.state.dragModeState.captureElement &&
        window.MemeManagerUI.state.dragModeState.pointerId !== null &&
        typeof window.MemeManagerUI.state.dragModeState.captureElement.setPointerCapture === "function"
      ) {
        try {
          window.MemeManagerUI.state.dragModeState.captureElement.setPointerCapture(
            window.MemeManagerUI.state.dragModeState.pointerId,
          );
        } catch {}
      }
      window.MemeManagerUI.emoji.ensureDragAutoScroll();
      window.MemeManagerUI.emoji.showDragHud({
        label: window.MemeManagerUI.emoji.getDragReadyLabel(dragItems.length),
        caption: "拖到目标分类，松手即可移动",
        progress: 1,
        clientX: pointerContext.clientX,
        clientY: pointerContext.clientY,
        state: "ready",
      });
    }

    window.MemeManagerUI.emoji.syncInteractionGuardState();

    window.MemeManagerUI.state.dragModeState.timeoutId = window.setTimeout(() => {
      window.MemeManagerUI.emoji.clearDragMode();
      window.MemeManagerUI.dialogs.showToast(
        "拖拽模式已自动退出，请重新长按进入。",
        "info",
        "拖拽模式已结束",
      );
    }, window.MemeManagerUI.state.DRAG_READY_TIMEOUT_MS);

    window.MemeManagerUI.dialogs.showToast(
      dragItems.length > 1
        ? `已进入拖拽模式，可拖动这 ${dragItems.length} 个表情包到目标分类。`
        : "已进入拖拽模式，可将表情包拖到目标分类。",
      "success",
      "拖拽模式已开启",
    );
  }
window.MemeManagerUI.emoji.startLongPress = function (emojiItem, category, emoji, event) {
    if (
      (event.pointerType === "mouse" && event.button !== 0) ||
      event.target.closest(".delete-btn")
    ) {
      return;
    }

    if (
      emojiItem.classList.contains("drag-ready") &&
      window.MemeManagerUI.state.dragModeState.items.length > 0
    ) {
      emojiItem.dataset.suppressClick = "true";
      if (typeof emojiItem.setPointerCapture === "function") {
        try {
          emojiItem.setPointerCapture(event.pointerId);
        } catch {}
      }
      window.MemeManagerUI.emoji.startPointerDrag(event);
      return;
    }

    const dragItems = window.MemeManagerUI.emoji.getDragItemsForEmoji(category, emoji);
    if (dragItems.length === 0) {
      return;
    }

    window.MemeManagerUI.emoji.cancelLongPress();
    if (
      window.MemeManagerUI.state.dragModeState.items.length > 0 &&
      !emojiItem.classList.contains("drag-ready")
    ) {
      window.MemeManagerUI.emoji.clearDragMode();
    }

    window.MemeManagerUI.state.longPressState.emojiItem = emojiItem;
    window.MemeManagerUI.state.longPressState.pointerId = event.pointerId;
    window.MemeManagerUI.state.longPressState.startTime = performance.now();
    window.MemeManagerUI.state.longPressState.startX = event.clientX;
    window.MemeManagerUI.state.longPressState.startY = event.clientY;
    window.MemeManagerUI.state.longPressState.currentX = event.clientX;
    window.MemeManagerUI.state.longPressState.currentY = event.clientY;

    emojiItem.classList.add("long-press-active");
    window.MemeManagerUI.emoji.syncInteractionGuardState();
    window.MemeManagerUI.emoji.setLongPressProgress(0, `${Math.ceil(window.MemeManagerUI.state.LONG_PRESS_DURATION_MS / 1000)}s`);

    window.MemeManagerUI.state.longPressState.intervalId = window.setInterval(() => {
      if (!window.MemeManagerUI.state.longPressState.emojiItem) {
        return;
      }

      const elapsed = performance.now() - window.MemeManagerUI.state.longPressState.startTime;
      const progress = elapsed / window.MemeManagerUI.state.LONG_PRESS_DURATION_MS;
      const remainingSeconds = Math.max(
        1,
        Math.ceil((window.MemeManagerUI.state.LONG_PRESS_DURATION_MS - elapsed) / 1000),
      );
      window.MemeManagerUI.emoji.setLongPressProgress(progress, `${remainingSeconds}s`);
    }, window.MemeManagerUI.state.LONG_PRESS_TICK_MS);

    window.MemeManagerUI.state.longPressState.timeoutId = window.setTimeout(() => {
      emojiItem.dataset.suppressClick = "true";
      const pointerContext = {
        pointerId: window.MemeManagerUI.state.longPressState.pointerId,
        clientX: window.MemeManagerUI.state.longPressState.currentX,
        clientY: window.MemeManagerUI.state.longPressState.currentY,
        sourceElement: emojiItem,
      };
      window.MemeManagerUI.emoji.cancelLongPress({ preserveReady: true, keepHud: true });
      window.MemeManagerUI.emoji.armDragMode(dragItems, pointerContext);
    }, window.MemeManagerUI.state.LONG_PRESS_DURATION_MS);
  }
window.MemeManagerUI.emoji.finishLongPress = function (event) {
    if (
      !window.MemeManagerUI.state.longPressState.emojiItem ||
      (typeof event.pointerId === "number" &&
        window.MemeManagerUI.state.longPressState.pointerId !== null &&
        event.pointerId !== window.MemeManagerUI.state.longPressState.pointerId)
    ) {
      return;
    }

    window.MemeManagerUI.emoji.cancelLongPress();
  }
window.MemeManagerUI.emoji.isInternalEmojiDrag = function (event) {
    const dragTypes = Array.from(event.dataTransfer?.types || []);
    return dragTypes.includes("application/x-meme-emoji");
  }
window.MemeManagerUI.emoji.getDraggedEmojiPayload = function (event) {
    try {
      const rawPayload = event.dataTransfer?.getData(
        "application/x-meme-emoji",
      );
      if (!rawPayload) {
        return null;
      }
      const payload = JSON.parse(rawPayload);
      if (Array.isArray(payload?.items) && payload.items.length > 0) {
        const items = window.MemeManagerUI.emoji.dedupeEmojiItems(payload.items);
        return items.length > 0 ? { items } : null;
      }
      if (!payload?.category || !payload?.emoji) {
        return null;
      }
      return { items: [{ category: payload.category, emoji: payload.emoji }] };
    } catch {
      return null;
    }
  }
window.MemeManagerUI.emoji.hasMoveableItemsForTarget = function (items, targetCategory) {
    return window.MemeManagerUI.emoji.dedupeEmojiItems(items).some(
      (item) => item.category !== targetCategory,
    );
  }
window.MemeManagerUI.emoji.clearCategoryDropHighlights = function () {
    document
      .querySelectorAll(".category-drop-active")
      .forEach((categoryDiv) => {
        categoryDiv.classList.remove("category-drop-active");
      });
  }
window.MemeManagerUI.emoji.normalizeUploadFiles = function (fileList) {
    const validFiles = [];
    let invalidCount = 0;

    Array.from(fileList || []).forEach((file) => {
      const isImageFile =
        file instanceof File &&
        (file.type.startsWith("image/") ||
          /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(file.name));

      if (isImageFile) {
        validFiles.push(file);
        return;
      }
      invalidCount += 1;
    });

    return { validFiles, invalidCount };
  }
window.MemeManagerUI.emoji.dedupeUploadFiles = function (files) {
    const uniqueFiles = [];
    const seenSignatures = new Set();
    let duplicateCount = 0;

    files.forEach((file) => {
      const signature = [
        file.name,
        file.size,
        file.lastModified,
        file.type,
      ].join("::");

      if (seenSignatures.has(signature)) {
        duplicateCount += 1;
        return;
      }

      seenSignatures.add(signature);
      uniqueFiles.push(file);
    });

    return { uniqueFiles, duplicateCount };
  }
window.MemeManagerUI.emoji.refreshUploadDropzones = function (category = null) {
    document.querySelectorAll(".emoji-upload").forEach((uploadBlock) => {
      if (category && uploadBlock.dataset.category !== category) {
        return;
      }

      const uploadTitle = uploadBlock.querySelector(".emoji-upload-title");
      const uploadHint = uploadBlock.querySelector(".emoji-upload-hint");
      const uploadMeta = uploadBlock.querySelector(".emoji-upload-meta");
      const uploadProgress = uploadBlock.querySelector(
        ".emoji-upload-progress",
      );
      const uploadProgressBar = uploadBlock.querySelector(
        ".emoji-upload-progress-bar",
      );
      const uploadIconInner = uploadBlock.querySelector(".emoji-upload-icon i");

      if (
        !uploadTitle ||
        !uploadHint ||
        !uploadMeta ||
        !uploadProgress ||
        !uploadProgressBar ||
        !uploadIconInner
      ) {
        return;
      }

      const state = window.MemeManagerUI.state.uploadStateByCategory.get(uploadBlock.dataset.category);

      if (!state) {
        uploadBlock.classList.remove("uploading");
        uploadBlock.setAttribute("aria-busy", "false");
        uploadTitle.textContent = "上传表情包";
        uploadHint.textContent = "点击上传图片，或将表情长按 2 秒后拖到这里";
        uploadMeta.textContent = "";
        uploadMeta.classList.add("hidden");
        uploadProgress.classList.add("hidden");
        uploadProgressBar.style.width = "0%";
        uploadIconInner.className = "fas fa-cloud-arrow-up";
        return;
      }

      const processedCount = state.completed + state.failed + state.duplicates;
      const currentIndex = Math.min(processedCount + 1, state.total);
      const progressPercent =
        state.total > 0 ? Math.round((processedCount / state.total) * 100) : 0;

      uploadBlock.classList.add("uploading");
      uploadBlock.setAttribute("aria-busy", "true");
      uploadIconInner.className = "fas fa-spinner fa-spin";
      uploadMeta.classList.remove("hidden");
      uploadProgress.classList.remove("hidden");
      uploadProgressBar.style.width = `${progressPercent}%`;

      if (state.refreshing) {
        uploadTitle.textContent = "正在刷新列表";
        uploadHint.textContent = `已处理 ${state.total} 个文件，正在更新界面`;
      } else {
        uploadTitle.textContent = `正在上传 ${currentIndex}/${state.total}`;
        uploadHint.textContent = state.currentFileName
          ? `当前文件：${state.currentFileName}`
          : "正在准备上传文件";
      }

      const metaParts = [`已完成 ${processedCount}/${state.total}`];
      if (state.duplicates > 0) {
        metaParts.push(`重复 ${state.duplicates}`);
      }
      if (state.failed > 0) {
        metaParts.push(`失败 ${state.failed}`);
      }
      uploadMeta.textContent = metaParts.join("，");
    });
  }
window.MemeManagerUI.emoji.isCategoryUploading = function (category) {
    return window.MemeManagerUI.state.uploadStateByCategory.has(category);
  }
window.MemeManagerUI.emoji.uploadFilesToCategory = async function (category, fileList) {
    const { validFiles, invalidCount } = window.MemeManagerUI.emoji.normalizeUploadFiles(fileList);

    if (invalidCount > 0) {
      window.MemeManagerUI.dialogs.showToast(
        `已忽略 ${invalidCount} 个非图片文件。`,
        "warning",
        "文件类型不支持",
      );
    }

    if (validFiles.length === 0) {
      return;
    }

    const { uniqueFiles, duplicateCount } = window.MemeManagerUI.emoji.dedupeUploadFiles(validFiles);

    if (duplicateCount > 0) {
      window.MemeManagerUI.dialogs.showToast(
        `已忽略本批次中 ${duplicateCount} 个重复文件。`,
        "info",
        "已自动去重",
      );
    }

    if (uniqueFiles.length === 0) {
      return;
    }

    if (window.MemeManagerUI.emoji.isCategoryUploading(category)) {
      window.MemeManagerUI.dialogs.showToast(
        `分类 ${category} 正在上传文件，请等待当前批次完成。`,
        "info",
        "上传进行中",
      );
      return;
    }

    const uploadState = {
      total: uniqueFiles.length,
      completed: 0,
      failed: 0,
      duplicates: 0,
      currentFileName: uniqueFiles[0]?.name || "",
      refreshing: false,
    };
    window.MemeManagerUI.state.uploadStateByCategory.set(category, uploadState);
    window.MemeManagerUI.emoji.refreshUploadDropzones(category);

    window.MemeManagerUI.dialogs.showToast(
      uniqueFiles.length > 1
        ? `开始向 ${category} 上传 ${uniqueFiles.length} 个文件。`
        : `开始向 ${category} 上传 1 个文件。`,
      "info",
      "上传开始",
      2200,
    );

    const failedUploads = [];
    const duplicateUploads = [];

    for (const file of uniqueFiles) {
      uploadState.currentFileName = file.name;
      window.MemeManagerUI.emoji.refreshUploadDropzones(category);

      try {
        await window.MemeManagerUI.emoji.uploadEmoji(category, file);
        uploadState.completed += 1;
      } catch (error) {
        if (error.code === "duplicate_emoji" || error.status === 409) {
          uploadState.duplicates += 1;
          duplicateUploads.push({ fileName: file.name, error });
        } else {
          uploadState.failed += 1;
          failedUploads.push({ fileName: file.name, error });
        }
      }

      window.MemeManagerUI.emoji.refreshUploadDropzones(category);
    }

    if (uploadState.completed > 0) {
      uploadState.refreshing = true;
      uploadState.currentFileName = "";
      window.MemeManagerUI.emoji.refreshUploadDropzones(category);
      await window.MemeManagerUI.emoji.refreshUi({ emojis: true });
    }

    window.MemeManagerUI.state.uploadStateByCategory.delete(category);
    window.MemeManagerUI.emoji.refreshUploadDropzones(category);

    if (uploadState.failed === 0 && uploadState.duplicates === 0) {
      window.MemeManagerUI.dialogs.showToast(
        uploadState.completed > 1
          ? `已向 ${category} 上传 ${uploadState.completed} 个文件。`
          : `已向 ${category} 上传 1 个文件。`,
        "success",
        "上传成功",
      );
      return;
    }

    if (uploadState.completed > 0 && uploadState.failed === 0) {
      window.MemeManagerUI.dialogs.showToast(
        `上传完成，新增 ${uploadState.completed} 个，跳过重复 ${uploadState.duplicates} 个。`,
        "warning",
        "上传已去重",
        4500,
      );
      return;
    }

    if (
      uploadState.completed === 0 &&
      uploadState.duplicates > 0 &&
      uploadState.failed === 0
    ) {
      const firstDuplicateMessage =
        duplicateUploads[0]?.error?.message || "这些文件已存在于当前分类";
      window.MemeManagerUI.dialogs.showToast(
        `未新增文件，已跳过 ${uploadState.duplicates} 个重复项：${firstDuplicateMessage}`,
        "info",
        "无需重复上传",
        4500,
      );
      return;
    }

    if (uploadState.completed > 0) {
      window.MemeManagerUI.dialogs.showToast(
        `上传完成，成功 ${uploadState.completed} 个，重复 ${uploadState.duplicates} 个，失败 ${uploadState.failed} 个。`,
        "warning",
        "部分上传失败",
        4500,
      );
      return;
    }

    const firstErrorMessage =
      failedUploads[0]?.error?.message || "服务器返回错误";
    window.MemeManagerUI.dialogs.showToast(
      `本次上传全部失败：${firstErrorMessage}`,
      "error",
      "上传失败",
      4500,
    );
  }
window.MemeManagerUI.emoji.createUploadDropzone = function (category) {
    const uploadBlock = document.createElement("div");
    uploadBlock.className = "emoji-upload";
    uploadBlock.dataset.category = category;
    uploadBlock.tabIndex = 0;
    uploadBlock.setAttribute("role", "button");
    uploadBlock.setAttribute(
      "aria-label",
      `上传 ${category} 分类表情包，支持点击选择或拖拽图片`,
    );

    const uploadIcon = document.createElement("div");
    uploadIcon.className = "emoji-upload-icon";
    const uploadIconInner = document.createElement("i");
    uploadIconInner.className = "fas fa-cloud-arrow-up";
    uploadIcon.appendChild(uploadIconInner);

    const uploadTitle = document.createElement("div");
    uploadTitle.className = "emoji-upload-title";
    uploadTitle.textContent = "上传表情包";

    const uploadHint = document.createElement("div");
    uploadHint.className = "emoji-upload-hint";
    uploadHint.textContent = "点击上传图片，或将表情长按 2 秒后拖到这里";

    const uploadMeta = document.createElement("div");
    uploadMeta.className = "emoji-upload-meta hidden";

    const uploadProgress = document.createElement("div");
    uploadProgress.className = "emoji-upload-progress hidden";
    const uploadProgressBar = document.createElement("span");
    uploadProgressBar.className = "emoji-upload-progress-bar";
    uploadProgress.appendChild(uploadProgressBar);

    uploadBlock.appendChild(uploadIcon);
    uploadBlock.appendChild(uploadTitle);
    uploadBlock.appendChild(uploadHint);
    uploadBlock.appendChild(uploadMeta);
    uploadBlock.appendChild(uploadProgress);

    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.style.display = "none";
    fileInput.accept = "image/*";
    fileInput.multiple = true;

    let dragDepth = 0;

    const setDragState = (active) => {
      uploadBlock.classList.toggle("drag-active", active);
    };

    uploadBlock.addEventListener("click", () => {
      if (window.MemeManagerUI.emoji.isCategoryUploading(category)) {
        window.MemeManagerUI.dialogs.showToast(
          `分类 ${category} 正在上传文件，请稍候。`,
          "info",
          "上传进行中",
        );
        return;
      }
      fileInput.click();
    });

    uploadBlock.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        if (window.MemeManagerUI.emoji.isCategoryUploading(category)) {
          window.MemeManagerUI.dialogs.showToast(
            `分类 ${category} 正在上传文件，请稍候。`,
            "info",
            "上传进行中",
          );
          return;
        }
        fileInput.click();
      }
    });

    fileInput.addEventListener("change", (event) => {
      void window.MemeManagerUI.emoji.uploadFilesToCategory(category, event.target.files);
      fileInput.value = "";
    });

    uploadBlock.addEventListener("dragenter", (event) => {
      if (window.MemeManagerUI.emoji.isInternalEmojiDrag(event)) {
        event.preventDefault();
        return;
      }
      event.preventDefault();
      dragDepth += 1;
      setDragState(true);
    });

    uploadBlock.addEventListener("dragover", (event) => {
      if (window.MemeManagerUI.emoji.isInternalEmojiDrag(event)) {
        event.preventDefault();
        return;
      }
      event.preventDefault();
      if (event.dataTransfer) {
        event.dataTransfer.dropEffect = "copy";
      }
      setDragState(true);
    });

    uploadBlock.addEventListener("dragleave", (event) => {
      if (window.MemeManagerUI.emoji.isInternalEmojiDrag(event)) {
        event.preventDefault();
        return;
      }
      event.preventDefault();
      dragDepth = Math.max(0, dragDepth - 1);
      if (dragDepth === 0) {
        setDragState(false);
      }
    });

    uploadBlock.addEventListener("drop", (event) => {
      if (window.MemeManagerUI.emoji.isInternalEmojiDrag(event)) {
        event.preventDefault();
        dragDepth = 0;
        setDragState(false);
        return;
      }
      event.preventDefault();
      dragDepth = 0;
      setDragState(false);
      if (window.MemeManagerUI.emoji.isCategoryUploading(category)) {
        window.MemeManagerUI.dialogs.showToast(
          `分类 ${category} 正在上传文件，请等待当前批次完成。`,
          "info",
          "上传进行中",
        );
        return;
      }
      void window.MemeManagerUI.emoji.uploadFilesToCategory(category, event.dataTransfer?.files);
    });

    window.MemeManagerUI.emoji.refreshUploadDropzones(category);

    return { uploadBlock, fileInput };
  }
window.MemeManagerUI.emoji.createDragProgressIndicator = function () {
    const indicator = document.createElement("div");
    indicator.className = "drag-progress-indicator";

    const ring = document.createElement("div");
    ring.className = "drag-progress-ring";

    const center = document.createElement("div");
    center.className = "drag-progress-center";

    const label = document.createElement("span");
    label.className = "drag-progress-label";
    label.textContent = "拖";

    center.appendChild(label);
    indicator.appendChild(ring);
    indicator.appendChild(center);

    return indicator;
  }
window.MemeManagerUI.emoji.bindEmojiInteractions = function (emojiItem, category, emoji) {
    const selectionIndicator = emojiItem.querySelector(".selection-indicator");
    if (selectionIndicator) {
      selectionIndicator.addEventListener("pointerdown", (event) => {
        event.stopPropagation();
      });
      selectionIndicator.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        if (!window.MemeManagerUI.state.selectionState.enabled) {
          window.MemeManagerUI.emoji.setSelectionMode(true);
        }
        window.MemeManagerUI.emoji.toggleEmojiSelection(category, emoji);
      });
    }

    emojiItem.addEventListener("click", () => {
      if (emojiItem.dataset.suppressClick === "true") {
        emojiItem.dataset.suppressClick = "false";
        return;
      }
      if (emojiItem.classList.contains("emoji-load-error")) {
        window.MemeManagerUI.emoji.retryEmojiPreview(emojiItem);
        return;
      }
      if (!window.MemeManagerUI.state.selectionState.enabled) {
        void window.MemeManagerUI.emoji.openImagePreview(
          category,
          emoji,
          emojiItem.dataset.previewDataUrl || "",
        );
        return;
      }
      window.MemeManagerUI.emoji.toggleEmojiSelection(category, emoji);
    });

    emojiItem.addEventListener("keydown", (event) => {
      if (!window.MemeManagerUI.state.selectionState.enabled) return;
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        window.MemeManagerUI.emoji.toggleEmojiSelection(category, emoji);
      }
    });

    emojiItem.addEventListener("pointerdown", (event) => {
      window.MemeManagerUI.emoji.startLongPress(emojiItem, category, emoji, event);
    });
  }
window.MemeManagerUI.emoji.closeMoveTargetModal = function () {
    if (window.MemeManagerUI.state.moveTargetModalRoot) {
      window.MemeManagerUI.state.moveTargetModalRoot.classList.add("hidden");
      window.MemeManagerUI.state.moveTargetModalRoot.setAttribute("aria-hidden", "true");
    }
    window.MemeManagerUI.state.pendingMoveTargetItems = [];
    if (window.MemeManagerUI.state.moveTargetList) {
      window.MemeManagerUI.state.moveTargetList.innerHTML = "";
    }
  }
window.MemeManagerUI.emoji.openMoveTargetModal = function (
    items = Array.from(window.MemeManagerUI.state.selectionState.items.values()),
  ) {
    const uniqueItems = window.MemeManagerUI.emoji.dedupeEmojiItems(items);
    if (uniqueItems.length === 0) {
      window.MemeManagerUI.dialogs.showToast("请先选择要移动的表情包。", "warning", "未选择项目");
      return;
    }

    const availableTargets = window.MemeManagerUI.emoji.getAvailableMoveTargets(uniqueItems);
    if (availableTargets.length === 0) {
      window.MemeManagerUI.dialogs.showToast("当前没有可移动到的其他分类。", "warning", "无法移动");
      return;
    }

    window.MemeManagerUI.state.pendingMoveTargetItems = uniqueItems;
    if (window.MemeManagerUI.state.moveTargetModalTitle) {
      window.MemeManagerUI.state.moveTargetModalTitle.textContent = "选择目标分类";
    }
    if (window.MemeManagerUI.state.moveTargetModalDescription) {
      window.MemeManagerUI.state.moveTargetModalDescription.textContent =
        uniqueItems.length > 1
          ? `已选 ${uniqueItems.length} 个表情包，选择要批量移动到的分类。`
          : "选择要移动到的目标分类。";
    }

    if (window.MemeManagerUI.state.moveTargetList) {
      window.MemeManagerUI.state.moveTargetList.innerHTML = "";
      availableTargets.forEach((category) => {
        const moveableCount = window.MemeManagerUI.emoji.getMoveableCountForTarget(uniqueItems, category);
        const optionButton = window.MemeManagerUI.emoji.createButton({
          className: "move-target-option",
          onClick: async () => {
            window.MemeManagerUI.emoji.closeMoveTargetModal();
            await window.MemeManagerUI.emoji.moveEmojiItemsToCategory(category, uniqueItems);
          },
        });

        const title = document.createElement("span");
        title.className = "move-target-option-title";
        title.textContent = category;

        const meta = document.createElement("span");
        meta.className = "move-target-option-meta";
        meta.textContent = `可移动 ${moveableCount} 个表情包`;

        optionButton.appendChild(title);
        optionButton.appendChild(meta);
        window.MemeManagerUI.state.moveTargetList.appendChild(optionButton);
      });
    }

    if (window.MemeManagerUI.state.moveTargetModalRoot) {
      window.MemeManagerUI.state.moveTargetModalRoot.classList.remove("hidden");
      window.MemeManagerUI.state.moveTargetModalRoot.setAttribute("aria-hidden", "false");
    }
  }
window.MemeManagerUI.emoji.moveEmojiItemsToCategory = async function (targetCategory, items) {
    if (!targetCategory) {
      window.MemeManagerUI.dialogs.showToast("请先选择目标分类。", "warning", "缺少目标分类");
      return;
    }

    const moveableItems = window.MemeManagerUI.emoji.dedupeEmojiItems(items).filter(
      (item) => item.category !== targetCategory,
    );
    if (moveableItems.length === 0) {
      window.MemeManagerUI.dialogs.showToast("当前选择的表情包已经都在目标分类中。", "warning", "无需移动");
      window.MemeManagerUI.emoji.clearDragMode();
      return;
    }

    window.MemeManagerUI.emoji.clearDragMode();

    const groupedItems = window.MemeManagerUI.emoji.groupEmojiItemsByCategory(moveableItems);

    let movedCount = 0;
    const movedKeys = [];
    const conflictFiles = [];
    const missingFiles = [];
    const requestErrors = [];

    for (const [sourceCategory, imageFiles] of groupedItems.entries()) {
      try {
        const data = await window.MemeManagerUI.api.apiPost("emoji/batch_move", {
          source_category: sourceCategory,
          target_category: targetCategory,
          image_files: imageFiles,
        });

        movedCount += data.moved_count || 0;
        (data.moved_files || []).forEach((filename) => {
          movedKeys.push(window.MemeManagerUI.emoji.createSelectionKey(sourceCategory, filename));
        });
        (data.conflicting_files || []).forEach((filename) => {
          conflictFiles.push(`${sourceCategory}/${filename}`);
        });
        (data.missing_files || []).forEach((filename) => {
          missingFiles.push(`${sourceCategory}/${filename}`);
        });
      } catch (error) {
        console.error("批量移动表情包失败", error);
        requestErrors.push(`${sourceCategory}: ${error.message}`);
      }
    }

    movedKeys.forEach((selectionKey) => {
      window.MemeManagerUI.state.selectionState.items.delete(selectionKey);
    });

    if (movedCount > 0) {
      await window.MemeManagerUI.emoji.refreshUi({ emojis: true });
    } else {
      window.MemeManagerUI.emoji.updateSelectionUI();
    }

    if (
      requestErrors.length > 0 ||
      conflictFiles.length > 0 ||
      missingFiles.length > 0
    ) {
      const messageParts = [`已成功移动 ${movedCount} 个表情包。`];
      if (conflictFiles.length > 0) {
        messageParts.push(`目标分类已存在：${conflictFiles.join("、")}`);
      }
      if (missingFiles.length > 0) {
        messageParts.push(`源文件不存在：${missingFiles.join("、")}`);
      }
      if (requestErrors.length > 0) {
        messageParts.push(`请求失败：${requestErrors.join("；")}`);
      }
      window.MemeManagerUI.dialogs.showToast(messageParts.join("\n"), "warning", "移动部分完成", 5600);
      return;
    }

    window.MemeManagerUI.dialogs.showToast(
      `已移动 ${movedCount} 个表情包到 ${targetCategory}`,
      "success",
      "移动成功",
    );
  }
window.MemeManagerUI.emoji.copyEmojiItemsToCategory = async function (targetCategory, items) {
    if (!targetCategory) {
      window.MemeManagerUI.dialogs.showToast("请先选择要粘贴到的分类。", "warning", "缺少目标分类");
      return;
    }

    const pasteableItems = window.MemeManagerUI.emoji.dedupeEmojiItems(items).filter(
      (item) => item.category !== targetCategory,
    );

    if (pasteableItems.length === 0) {
      window.MemeManagerUI.dialogs.showToast("当前没有可粘贴到该分类的文件。", "warning", "无需粘贴");
      return;
    }

    const groupedItems = window.MemeManagerUI.emoji.groupEmojiItemsByCategory(pasteableItems);
    let copiedCount = 0;
    const conflictFiles = [];
    const missingFiles = [];
    const requestErrors = [];

    for (const [sourceCategory, imageFiles] of groupedItems.entries()) {
      try {
        const data = await window.MemeManagerUI.api.apiPost("emoji/batch_copy", {
          source_category: sourceCategory,
          target_category: targetCategory,
          image_files: imageFiles,
        });

        copiedCount += data.copied_count || 0;
        (data.conflicting_files || []).forEach((filename) => {
          conflictFiles.push(`${sourceCategory}/${filename}`);
        });
        (data.missing_files || []).forEach((filename) => {
          missingFiles.push(`${sourceCategory}/${filename}`);
        });
      } catch (error) {
        console.error("批量复制表情包失败", error);
        requestErrors.push(`${sourceCategory}: ${error.message}`);
      }
    }

    if (copiedCount > 0) {
      await window.MemeManagerUI.emoji.refreshUi({ emojis: true });
    }

    if (
      requestErrors.length > 0 ||
      conflictFiles.length > 0 ||
      missingFiles.length > 0
    ) {
      const messageParts = [`已成功粘贴 ${copiedCount} 个表情包。`];
      if (conflictFiles.length > 0) {
        messageParts.push(`目标分类已存在：${conflictFiles.join("、")}`);
      }
      if (missingFiles.length > 0) {
        messageParts.push(`源文件不存在：${missingFiles.join("、")}`);
      }
      if (requestErrors.length > 0) {
        messageParts.push(`请求失败：${requestErrors.join("；")}`);
      }
      window.MemeManagerUI.dialogs.showToast(messageParts.join("\n"), "warning", "粘贴部分完成", 5600);
      return;
    }

    window.MemeManagerUI.dialogs.showToast(
      `已粘贴 ${copiedCount} 个表情包到 ${targetCategory}`,
      "success",
      "粘贴成功",
    );
  }
window.MemeManagerUI.emoji.attachCategoryDropTarget = function (categoryDiv, category) {
    let dragDepth = 0;

    const setActive = (active) => {
      categoryDiv.classList.toggle("category-drop-active", active);
    };

    categoryDiv.addEventListener("dragenter", (event) => {
      if (!window.MemeManagerUI.emoji.isInternalEmojiDrag(event)) {
        return;
      }

      const payload = window.MemeManagerUI.emoji.getDraggedEmojiPayload(event);
      if (!payload || !window.MemeManagerUI.emoji.hasMoveableItemsForTarget(payload.items, category)) {
        return;
      }

      event.preventDefault();
      dragDepth += 1;
      setActive(true);
    });

    categoryDiv.addEventListener("dragover", (event) => {
      if (!window.MemeManagerUI.emoji.isInternalEmojiDrag(event)) {
        return;
      }

      const payload = window.MemeManagerUI.emoji.getDraggedEmojiPayload(event);
      if (!payload || !window.MemeManagerUI.emoji.hasMoveableItemsForTarget(payload.items, category)) {
        return;
      }

      event.preventDefault();
      if (event.dataTransfer) {
        event.dataTransfer.dropEffect = "move";
      }
      setActive(true);
    });

    categoryDiv.addEventListener("dragleave", (event) => {
      if (!window.MemeManagerUI.emoji.isInternalEmojiDrag(event)) {
        return;
      }

      event.preventDefault();
      dragDepth = Math.max(0, dragDepth - 1);
      if (dragDepth === 0) {
        setActive(false);
      }
    });

    categoryDiv.addEventListener("drop", async (event) => {
      if (!window.MemeManagerUI.emoji.isInternalEmojiDrag(event)) {
        return;
      }

      const payload = window.MemeManagerUI.emoji.getDraggedEmojiPayload(event);
      dragDepth = 0;
      setActive(false);
      if (!payload || !window.MemeManagerUI.emoji.hasMoveableItemsForTarget(payload.items, category)) {
        return;
      }

      event.preventDefault();
      await window.MemeManagerUI.emoji.moveEmojiItemsToCategory(category, payload.items);
    });
  }
window.MemeManagerUI.emoji.displayCategories = function (emojiData, tagDescriptions) {
    const container = document.getElementById("emoji-categories");
    container.innerHTML = "";

    const categoryEntries = Object.entries(emojiData || {}).map(([category, emojis]) => [
      category,
      Array.isArray(emojis) ? emojis : [],
    ]);
    const totalEmojiCount = categoryEntries.reduce((total, [, emojis]) => {
      return total + (Array.isArray(emojis) ? emojis.length : 0);
    }, 0);

    if (!categoryEntries.length || totalEmojiCount === 0) {
      const hint = document.createElement("div");
      hint.className = "empty-pack-hint";
      hint.innerHTML = `
        <p class="empty-pack-hint-title">当前还没有表情包内容</p>
        <p class="empty-pack-hint-meta">你可以直接上传图片并选择固定标签，或前往资源广场下载官方包。</p>
        <div class="empty-pack-hint-actions">
          <button id="empty-hint-install-official" type="button">一键安装官方包</button>
          <a id="empty-hint-open-catalog" href="#">前往资源广场下载</a>
        </div>
      `;
      container.appendChild(hint);

      if (!window.MemeManagerUI.state.emptyPackGuideShown) {
        window.MemeManagerUI.dialogs.showToast(
          "当前是空表情包，建议前往资源广场下载官方包。",
          "info",
          "提示",
        );
        window.MemeManagerUI.state.emptyPackGuideShown = true;
      }

      const installOfficialBtn = document.getElementById(
        "empty-hint-install-official",
      );
      installOfficialBtn?.addEventListener("click", async () => {
        await window.MemeManagerUI.pack.installOfficialFirstPackFromHint(installOfficialBtn);
      });

      const openCatalogLink = document.getElementById(
        "empty-hint-open-catalog",
      );
      if (openCatalogLink) {
        openCatalogLink.href = window.MemeManagerUI.pack.buildCatalogPageUrl();
      }
    }

    categoryEntries.forEach(([category, emojis]) => {
      const categoryDiv = document.createElement("div");
      categoryDiv.className = "category";
      categoryDiv.id = `category-${category}`;
      categoryDiv.dataset.category = category;

      const description = tagDescriptions[category] || `请添加描述`;
      const titleDiv = document.createElement("div");
      titleDiv.className = "category-title";
      const categorySelectedCount = window.MemeManagerUI.emoji.getCategorySelectedCount(category);
      const allSelectedInCategory =
        Array.isArray(emojis) &&
        emojis.length > 0 &&
        emojis.every((emoji) => window.MemeManagerUI.emoji.isEmojiSelected(category, emoji));
      const headerDiv = document.createElement("div");
      headerDiv.className = "category-header";

      const titleMain = document.createElement("div");
      titleMain.className = "category-title-main";

      const categoryName = document.createElement("div");
      categoryName.className = "category-name";
      categoryName.id = `category-name-${category}`;
      categoryName.textContent = category;

      const selectionSummary = document.createElement("span");
      window.MemeManagerUI.state.selectionSummary.className = "category-selection-summary";
      window.MemeManagerUI.state.selectionSummary.id = `category-selection-summary-${category}`;
      window.MemeManagerUI.state.selectionSummary.textContent = window.MemeManagerUI.state.selectionState.enabled
        ? `已选 ${categorySelectedCount} / ${emojis.length || 0}`
        : "未开启批量选择";

      titleMain.appendChild(categoryName);
      titleMain.appendChild(window.MemeManagerUI.state.selectionSummary);

      const actionsDiv = document.createElement("div");
      actionsDiv.className = "category-actions";

      const editButton = window.MemeManagerUI.emoji.createButton({
        className: "edit-category-btn",
        text: "编辑类别",
        onClick: () => window.MemeManagerUI.emoji.editCategory(category),
      });
      const toggleCategoryButton = window.MemeManagerUI.emoji.createButton({
        className: "select-all-category-btn",
        text: window.MemeManagerUI.state.selectionState.enabled
          ? allSelectedInCategory
            ? "取消本类"
            : "本类全选"
          : "本类选择",
        disabled: !Array.isArray(emojis) || emojis.length === 0,
        onClick: () => window.MemeManagerUI.emoji.toggleCategorySelection(category, emojis),
      });
      const clearCategoryButton = window.MemeManagerUI.emoji.createButton({
        className: "clear-category-btn danger",
        text: "清空本类",
        onClick: () => window.MemeManagerUI.emoji.clearCategory(category),
      });
      editButton.hidden = false;
      clearCategoryButton.hidden = false;
      actionsDiv.appendChild(editButton);
      actionsDiv.appendChild(toggleCategoryButton);
      actionsDiv.appendChild(clearCategoryButton);

      headerDiv.appendChild(titleMain);
      headerDiv.appendChild(actionsDiv);

      const descriptionElement = document.createElement("p");
      descriptionElement.className = "description";
      descriptionElement.id = `category-desc-${category}`;
      descriptionElement.textContent = description;

      titleDiv.appendChild(headerDiv);
      titleDiv.appendChild(descriptionElement);
      categoryDiv.appendChild(titleDiv);

      const emojiGrid = document.createElement("div");
      emojiGrid.className = "emoji-grid";

      // emojis 是数组
      if (Array.isArray(emojis)) {
        emojis.forEach((emoji) => {
          const emojiItem = document.createElement("div");
          emojiItem.className = "emoji-item";
          emojiItem.dataset.category = category;
          emojiItem.dataset.emoji = emoji;
          emojiItem.dataset.suppressClick = "false";
          emojiItem.dataset.loading = "false";
          emojiItem.tabIndex = 0;

          const selectionIndicator = document.createElement("button");
          selectionIndicator.type = "button";
          selectionIndicator.className = "selection-indicator";
          selectionIndicator.setAttribute("aria-label", "选择表情包");
          emojiItem.appendChild(selectionIndicator);

          // 删除按钮
          const deleteBtn = document.createElement("button");
          deleteBtn.className = "delete-btn";
          deleteBtn.innerHTML = "×";
          deleteBtn.onclick = (e) => {
            e.stopPropagation();
            window.MemeManagerUI.emoji.deleteEmoji(category, emoji);
          };
          emojiItem.appendChild(deleteBtn);
          window.MemeManagerUI.emoji.bindEmojiInteractions(emojiItem, category, emoji);

          window.MemeManagerUI.emoji.setEmojiPreviewLoading(emojiItem);
          emojiGrid.appendChild(emojiItem);
        });
      }

      if (true) {
        const { uploadBlock, fileInput } = window.MemeManagerUI.emoji.createUploadDropzone(category);

        // 筛选状态下不显示上传入口，避免把新图片误认为筛选结果。
        emojiGrid.appendChild(uploadBlock);
        emojiGrid.appendChild(fileInput);
      }

      categoryDiv.appendChild(emojiGrid);
      window.MemeManagerUI.emoji.attachCategoryDropTarget(categoryDiv, category);
      container.appendChild(categoryDiv);
    });

    const lazyBackgrounds = container.querySelectorAll(".emoji-item");
    const observer = new IntersectionObserver(
      (entries, observer) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            void window.MemeManagerUI.emoji.loadEmojiPreview(entry.target);
            observer.unobserve(entry.target);
          }
        });
      },
      {
        rootMargin: "220px 0px",
        threshold: 0.01,
      },
    );

    lazyBackgrounds.forEach((item) => {
      observer.observe(item);
    });

    window.MemeManagerUI.emoji.updateSelectionDecorations();
  }
window.MemeManagerUI.emoji.updateSidebar = function (data, tagDescriptions) {
    const sidebarList = document.getElementById("sidebar-list");
    if (!sidebarList) return;
    sidebarList.innerHTML = "";

    for (const category in data) {
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = "#category-" + category;
      a.textContent = category;
      a.addEventListener("click", () => {
        if (window.MemeManagerUI.emoji.isCompactViewport()) {
          window.MemeManagerUI.emoji.closeAllPanels();
          window.MemeManagerUI.emoji.updatePanelToggleState();
        }
      });
      li.appendChild(a);
      sidebarList.appendChild(li);
    }
  }
window.MemeManagerUI.emoji.createSelectionKey = function (category, emoji) {
    return `${category}::${emoji}`;
  }
window.MemeManagerUI.emoji.isEmojiSelected = function (category, emoji) {
    return window.MemeManagerUI.state.selectionState.items.has(window.MemeManagerUI.emoji.createSelectionKey(category, emoji));
  }
window.MemeManagerUI.emoji.getCategorySelectedCount = function (category) {
    let count = 0;
    window.MemeManagerUI.state.selectionState.items.forEach((item) => {
      if (item.category === category) {
        count += 1;
      }
    });
    return count;
  }
window.MemeManagerUI.emoji.pruneSelectionState = function () {
    const availableKeys = new Set();
    Object.entries(window.MemeManagerUI.state.latestEmojiData).forEach(([category, emojis]) => {
      if (!Array.isArray(emojis)) return;
      emojis.forEach((emoji) => {
        availableKeys.add(window.MemeManagerUI.emoji.createSelectionKey(category, emoji));
      });
    });

    Array.from(window.MemeManagerUI.state.selectionState.items.keys()).forEach((key) => {
      if (!availableKeys.has(key)) {
        window.MemeManagerUI.state.selectionState.items.delete(key);
      }
    });
  }
window.MemeManagerUI.emoji.updateSelectionToolbar = function () {
    const selectedCount = window.MemeManagerUI.state.selectionState.items.size;
    const availableMoveTargets = window.MemeManagerUI.emoji.getAvailableMoveTargets();

    if (window.MemeManagerUI.state.selectionSummary) {
      window.MemeManagerUI.state.selectionSummary.textContent = window.MemeManagerUI.state.selectionState.enabled
        ? `已选中 ${selectedCount} 个表情包`
        : "未开启批量选择";
    }
    if (window.MemeManagerUI.state.toggleSelectionModeBtn) {
      window.MemeManagerUI.state.toggleSelectionModeBtn.textContent = window.MemeManagerUI.state.selectionState.enabled
        ? "退出批量选择"
        : "开启批量选择";
    }
    if (window.MemeManagerUI.state.batchDeleteBtn) {
      window.MemeManagerUI.state.batchDeleteBtn.disabled = !window.MemeManagerUI.state.selectionState.enabled || selectedCount === 0;
    }
    if (window.MemeManagerUI.state.batchMoveBtn) {
      window.MemeManagerUI.state.batchMoveBtn.disabled =
        !window.MemeManagerUI.state.selectionState.enabled ||
        selectedCount === 0 ||
        availableMoveTargets.length === 0;
    }
  }
window.MemeManagerUI.emoji.updateSelectionDecorations = function () {
    document.querySelectorAll(".emoji-item").forEach((emojiItem) => {
      const category = emojiItem.dataset.category;
      const emoji = emojiItem.dataset.emoji;
      const selected = window.MemeManagerUI.emoji.isEmojiSelected(category, emoji);
      const selectionIndicator = emojiItem.querySelector(
        ".selection-indicator",
      );

      emojiItem.classList.toggle("selection-mode", window.MemeManagerUI.state.selectionState.enabled);
      emojiItem.classList.toggle("selected", selected);
      if (selectionIndicator) {
        selectionIndicator.classList.toggle("checked", selected);
        selectionIndicator.setAttribute(
          "aria-label",
          selected ? "已选中" : "未选择",
        );
      }
    });

    document.querySelectorAll(".category").forEach((categoryDiv) => {
      const category = categoryDiv.dataset.category;
      const totalCount = Array.isArray(window.MemeManagerUI.state.latestEmojiData[category])
        ? window.MemeManagerUI.state.latestEmojiData[category].length
        : 0;
      const selectedCount = window.MemeManagerUI.emoji.getCategorySelectedCount(category);
      const summary = categoryDiv.querySelector(".category-selection-summary");
      const selectAllBtn = categoryDiv.querySelector(
        ".select-all-category-btn",
      );
      const hasEmojis = totalCount > 0;
      const allSelected = hasEmojis && selectedCount === totalCount;

      if (summary) {
        summary.textContent = window.MemeManagerUI.state.selectionState.enabled
          ? `已选 ${selectedCount} / ${totalCount}`
          : "未开启批量选择";
      }
      if (selectAllBtn) {
        selectAllBtn.disabled = !hasEmojis;
        selectAllBtn.textContent = window.MemeManagerUI.state.selectionState.enabled
          ? allSelected
            ? "取消本类"
            : "本类全选"
          : "本类选择";
      }
    });
  }
window.MemeManagerUI.emoji.updateSelectionUI = function () {
    window.MemeManagerUI.emoji.updateSelectionToolbar();
    window.MemeManagerUI.emoji.updateSelectionDecorations();
  }
window.MemeManagerUI.emoji.clearSelections = function () {
    window.MemeManagerUI.emoji.clearDragMode();
    window.MemeManagerUI.emoji.closeMoveTargetModal();
    window.MemeManagerUI.emoji.closeBatchContextMenu();
    window.MemeManagerUI.state.selectionState.items.clear();
    window.MemeManagerUI.emoji.updateSelectionUI();
  }
window.MemeManagerUI.emoji.setSelectionMode = function (enabled) {
    window.MemeManagerUI.emoji.clearDragMode();
    window.MemeManagerUI.emoji.closeMoveTargetModal();
    window.MemeManagerUI.emoji.closeBatchContextMenu();
    window.MemeManagerUI.state.selectionState.enabled = enabled;
    if (!enabled) {
      window.MemeManagerUI.state.selectionState.items.clear();
    }
    window.MemeManagerUI.emoji.updateSelectionUI();
  }
window.MemeManagerUI.emoji.toggleEmojiSelection = function (category, emoji) {
    window.MemeManagerUI.emoji.clearDragMode();
    window.MemeManagerUI.emoji.closeMoveTargetModal();
    window.MemeManagerUI.emoji.closeBatchContextMenu();
    const selectionKey = window.MemeManagerUI.emoji.createSelectionKey(category, emoji);
    if (window.MemeManagerUI.state.selectionState.items.has(selectionKey)) {
      window.MemeManagerUI.state.selectionState.items.delete(selectionKey);
    } else {
      window.MemeManagerUI.state.selectionState.items.set(selectionKey, { category, emoji });
    }
    window.MemeManagerUI.emoji.updateSelectionUI();
  }
window.MemeManagerUI.emoji.toggleCategorySelection = function (category, emojis) {
    if (!Array.isArray(emojis) || emojis.length === 0) {
      return;
    }

    window.MemeManagerUI.emoji.clearDragMode();
    window.MemeManagerUI.emoji.closeMoveTargetModal();
    window.MemeManagerUI.emoji.closeBatchContextMenu();
    if (!window.MemeManagerUI.state.selectionState.enabled) {
      window.MemeManagerUI.emoji.setSelectionMode(true);
    }

    const allSelected = emojis.every((emoji) =>
      window.MemeManagerUI.emoji.isEmojiSelected(category, emoji),
    );
    emojis.forEach((emoji) => {
      const selectionKey = window.MemeManagerUI.emoji.createSelectionKey(category, emoji);
      if (allSelected) {
        window.MemeManagerUI.state.selectionState.items.delete(selectionKey);
      } else {
        window.MemeManagerUI.state.selectionState.items.set(selectionKey, { category, emoji });
      }
    });
    window.MemeManagerUI.emoji.updateSelectionUI();
  }
window.MemeManagerUI.emoji.getSelectedItemsByCategory = function () {
    const groupedSelections = new Map();
    window.MemeManagerUI.state.selectionState.items.forEach(({ category, emoji }) => {
      if (!groupedSelections.has(category)) {
        groupedSelections.set(category, []);
      }
      groupedSelections.get(category).push(emoji);
    });
    return groupedSelections;
  }
window.MemeManagerUI.emoji.copyItemsToClipboard = function (items) {
    const uniqueItems = window.MemeManagerUI.emoji.dedupeEmojiItems(items);
    if (uniqueItems.length === 0) {
      window.MemeManagerUI.dialogs.showToast("请先选择要复制的表情包。", "warning", "未选择项目");
      return false;
    }

    window.MemeManagerUI.emoji.setClipboardItems(uniqueItems);
    window.MemeManagerUI.dialogs.showToast(
      uniqueItems.length > 1
        ? `已复制 ${uniqueItems.length} 个表情包，可在目标分类右键后粘贴。`
        : "已复制 1 个表情包，可在目标分类右键后粘贴。",
      "success",
      "已复制到批量剪贴板",
    );
    return true;
  }
window.MemeManagerUI.emoji.uploadEmoji = async function (category, file) {
    const managedPackId = window.MemeManagerUI.api.getSelectedPackId();
    const query = managedPackId
      ? `?managed_pack_id=${encodeURIComponent(managedPackId)}`
      : "";
    return await window.AstrBotPluginPage.upload(
      "emoji/add/" + encodeURIComponent(category) + query,
      file,
    );
  }
window.MemeManagerUI.emoji.deleteEmoji = async function (category, emoji) {
    const confirmed = await window.MemeManagerUI.dialogs.showConfirm({
      title: "删除表情包",
      description: `确认删除分类「${category}」中的表情包「${emoji}」？此操作不可恢复。`,
      confirmLabel: "确认删除",
      confirmClassName: "danger",
    });
    if (!confirmed) return;

    try {
      const data = await window.MemeManagerUI.api.apiPost("emoji/delete", {
        category,
        image_file: emoji,
      });
      window.MemeManagerUI.state.selectionState.items.delete(window.MemeManagerUI.emoji.createSelectionKey(category, emoji));
      await window.MemeManagerUI.emoji.refreshUi({ emojis: true });
      window.MemeManagerUI.dialogs.showToast(
        `已从 ${data.category} 删除 ${data.filename}`,
        "success",
        "删除成功",
      );
    } catch (error) {
      console.error("删除表情包失败", error);
      window.MemeManagerUI.dialogs.showToast(`删除表情包失败：${error.message}`, "error", "删除失败", 4500);
    }
  }
window.MemeManagerUI.emoji.deleteEmojiItems = async function (
    items,
    { useSelectionState = true, confirmMode = "normal" } = {},
  ) {
    const uniqueItems = window.MemeManagerUI.emoji.dedupeEmojiItems(items);
    const selectedCount = uniqueItems.length;
    if (selectedCount === 0) {
      window.MemeManagerUI.dialogs.showToast("请先选择要删除的表情包", "warning", "未选择项目");
      return;
    }

    const confirmDescription = `确认删除已选中的 ${selectedCount} 个表情包？未成功删除的项目会保留选中状态。`;
    const confirmed =
      confirmMode === "danger"
        ? await window.MemeManagerUI.dialogs.showDangerConfirm({
            title: "批量删除表情包",
            description: confirmDescription,
            actionLabel: "确认删除已选文件",
            countdown: 5,
          })
        : await window.MemeManagerUI.dialogs.showConfirm({
            title: "批量删除表情包",
            description: confirmDescription,
            confirmLabel: "确认批量删除",
            confirmClassName: "danger",
          });
    if (!confirmed) {
      return;
    }

    let deletedCount = 0;
    const errors = [];
    const deletedKeys = [];
    const groupedSelections = window.MemeManagerUI.emoji.groupEmojiItemsByCategory(uniqueItems);

    for (const [category, imageFiles] of groupedSelections.entries()) {
      try {
        const data = await window.MemeManagerUI.api.apiPost("emoji/batch_delete", {
          category,
          image_files: imageFiles,
        });
        deletedCount += data.deleted_count || 0;
        (data.deleted_files || []).forEach((filename) => {
          deletedKeys.push(window.MemeManagerUI.emoji.createSelectionKey(category, filename));
        });
      } catch (error) {
        console.error("批量删除失败", error);
        errors.push(`${category}: ${error.message}`);
      }
    }

    if (useSelectionState) {
      deletedKeys.forEach((selectionKey) => {
        window.MemeManagerUI.state.selectionState.items.delete(selectionKey);
      });
    }

    if (deletedCount > 0) {
      await window.MemeManagerUI.emoji.refreshUi({ emojis: true });
    } else {
      window.MemeManagerUI.emoji.updateSelectionUI();
    }

    if (errors.length > 0) {
      window.MemeManagerUI.dialogs.showToast(
        `已删除 ${deletedCount} 个表情包。\n失败分类：${errors.join("；")}`,
        "warning",
        "批量删除部分完成",
        5200,
      );
      return;
    }

    window.MemeManagerUI.dialogs.showToast(`已删除 ${deletedCount} 个表情包`, "success", "批量删除完成");
  }
window.MemeManagerUI.emoji.batchDeleteSelected = async function () {
    await window.MemeManagerUI.emoji.deleteEmojiItems(Array.from(window.MemeManagerUI.state.selectionState.items.values()));
  }
window.MemeManagerUI.emoji.clearCategory = async function (category) {
    const emojiCount = Array.isArray(window.MemeManagerUI.state.latestEmojiData[category])
      ? window.MemeManagerUI.state.latestEmojiData[category].length
      : 0;
    if (emojiCount === 0) {
      window.MemeManagerUI.dialogs.showToast(
        `分类 ${category} 当前没有可清空的表情包`,
        "warning",
        "无需清空",
      );
      return;
    }

    const confirmed = await window.MemeManagerUI.dialogs.showDangerConfirm({
      title: `清空分类「${category}」`,
      description: `该操作会移除分类「${category}」下 ${emojiCount} 个表情包的标签关联，但会保留图片文件。`,
      actionLabel: "确认清空当前分类",
      countdown: 5,
    });
    if (!confirmed) {
      return;
    }

    try {
      const data = await window.MemeManagerUI.api.apiPost("category/clear", { category });
      window.MemeManagerUI.emoji.clearSelections();
      await window.MemeManagerUI.emoji.refreshUi({ emojis: true });
      window.MemeManagerUI.dialogs.showToast(
        `已清空标签 ${category}，移除 ${data.untagged_count || 0} 个标签关联，图片文件保留。`,
        "success",
        "清空成功",
      );
    } catch (error) {
      console.error("清空分类失败:", error);
      window.MemeManagerUI.dialogs.showToast(`清空分类失败：${error.message}`, "error", "清空失败", 4500);
    }
  }
window.MemeManagerUI.emoji.clearAllEmojiFiles = async function () {
    const totalEmojiCount = Object.values(window.MemeManagerUI.state.latestEmojiData).reduce(
      (sum, emojis) => sum + (Array.isArray(emojis) ? emojis.length : 0),
      0,
    );
    if (totalEmojiCount === 0) {
      window.MemeManagerUI.dialogs.showToast("当前没有可清空的表情包", "warning", "无需清空");
      return;
    }

    const confirmed = await window.MemeManagerUI.dialogs.showDangerConfirm({
      title: "清空全部表情包",
      description: `该操作会删除全部 ${totalEmojiCount} 个表情包，但保留现有分类目录和描述配置。`,
      actionLabel: "确认清空全部表情包",
      countdown: 5,
    });
    if (!confirmed) {
      return;
    }

    try {
      const data = await window.MemeManagerUI.api.apiPost("emoji/clear_all");
      window.MemeManagerUI.emoji.clearSelections();
      await window.MemeManagerUI.emoji.refreshUi({ emojis: true });
      window.MemeManagerUI.dialogs.showToast(
        `已清空全部表情包，共删除 ${data.deleted_count} 个文件，涉及 ${data.affected_categories} 个分类。`,
        "success",
        "清空成功",
        4200,
      );
    } catch (error) {
      console.error("清空全部表情包失败:", error);
      window.MemeManagerUI.dialogs.showToast(
        `清空全部表情包失败：${error.message}`,
        "error",
        "清空失败",
        4500,
      );
    }
  }
window.MemeManagerUI.emoji.handlePointerRelease = async (event) => {
    window.MemeManagerUI.emoji.finishLongPress(event);
    await window.MemeManagerUI.emoji.finishPointerDrag(event);
  };
window.MemeManagerUI.emoji.closeCategoryEditModal = function () {
    if (window.MemeManagerUI.state.categoryEditModalRoot) {
      window.MemeManagerUI.state.categoryEditModalRoot.classList.add("hidden");
      window.MemeManagerUI.state.categoryEditModalRoot.setAttribute("aria-hidden", "true");
    }
    window.MemeManagerUI.state.activeCategoryEdit = null;
    if (window.MemeManagerUI.state.categoryEditNameInput) {
      window.MemeManagerUI.state.categoryEditNameInput.value = "";
    }
    if (window.MemeManagerUI.state.categoryEditDescInput) {
      window.MemeManagerUI.state.categoryEditDescInput.value = "";
    }
  }
window.MemeManagerUI.emoji.editCategory = function (category) {
    const currentDescription = document
      .getElementById(`category-desc-${category}`)
      ?.textContent?.trim();

    window.MemeManagerUI.state.activeCategoryEdit = category;
    if (window.MemeManagerUI.state.categoryEditModalTitle) {
      window.MemeManagerUI.state.categoryEditModalTitle.textContent = `编辑类别「${category}」`;
    }
    if (window.MemeManagerUI.state.categoryEditModalDescription) {
      window.MemeManagerUI.state.categoryEditModalDescription.textContent =
        "仅可修改标签描述，标签名称保持固定。";
    }
    if (window.MemeManagerUI.state.categoryEditNameInput) {
      window.MemeManagerUI.state.categoryEditNameInput.value = category;
    }
    if (window.MemeManagerUI.state.categoryEditDescInput) {
      window.MemeManagerUI.state.categoryEditDescInput.value =
        currentDescription && currentDescription !== "请添加描述"
          ? currentDescription
          : "";
    }
    if (window.MemeManagerUI.state.categoryEditModalRoot) {
      window.MemeManagerUI.state.categoryEditModalRoot.classList.remove("hidden");
      window.MemeManagerUI.state.categoryEditModalRoot.setAttribute("aria-hidden", "false");
    }
    window.setTimeout(() => {
      window.MemeManagerUI.state.categoryEditDescInput?.focus();
    }, 0);
  }
window.MemeManagerUI.emoji.cancelEdit = function () {
    window.MemeManagerUI.emoji.closeCategoryEditModal();
  }
window.MemeManagerUI.emoji.saveCategory = async function (oldName = window.MemeManagerUI.state.activeCategoryEdit) {
    const newDesc = window.MemeManagerUI.state.categoryEditDescInput?.value.trim() || "";

    if (!oldName) {
      window.MemeManagerUI.dialogs.showToast("未找到当前正在编辑的类别。", "error", "保存失败");
      return;
    }

    window.MemeManagerUI.emoji.setButtonBusy(window.MemeManagerUI.state.categoryEditSaveBtn, "保存中...");

    try {
      await window.MemeManagerUI.api.apiPost("category/update_description", {
        tag: oldName,
        description: newDesc,
      });

      await window.MemeManagerUI.emoji.refreshUi({ emojis: true, syncStatus: true });
      window.MemeManagerUI.emoji.closeCategoryEditModal();
      window.MemeManagerUI.dialogs.showToast(`标签「${oldName}」的描述已保存。`, "success", "保存成功");
    } catch (error) {
      console.error("保存类别修改失败:", error);
      window.MemeManagerUI.dialogs.showToast(error.message, "error", "保存失败");
    } finally {
      window.MemeManagerUI.emoji.restoreButton(window.MemeManagerUI.state.categoryEditSaveBtn);
    }
  }
