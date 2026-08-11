window.MemeManagerUI = window.MemeManagerUI || {};
window.MemeManagerUI.emoji = window.MemeManagerUI.emoji || {};

window.MemeManagerUI.emoji.createButton = function ({
  className = "",
  text = "",
  disabled = false,
  onClick = null,
}) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.textContent = text;
  button.disabled = disabled;
  if (onClick) button.addEventListener("click", onClick);
  return button;
};

window.MemeManagerUI.emoji.setButtonBusy = function (button, busyText) {
  if (!button) return;
  if (!button.dataset.originalHtml) button.dataset.originalHtml = button.innerHTML;
  button.disabled = true;
  button.textContent = busyText;
};

window.MemeManagerUI.emoji.restoreButton = function (button) {
  if (!button) return;
  button.disabled = false;
  if (button.dataset.originalHtml) button.innerHTML = button.dataset.originalHtml;
};

window.MemeManagerUI.emoji.fetchEmojis = async function () {
  window.MemeManagerUI.state.loading = true;
  window.MemeManagerUI.state.error = null;
  try {
    const [emojiResult, descriptionsResult] = await Promise.allSettled([
      window.MemeManagerUI.api.apiGet("emoji"),
      window.MemeManagerUI.api.apiGet("emotions"),
    ]);
    if (emojiResult.status !== "fulfilled") {
      throw emojiResult.reason || new Error("表情包目录加载失败");
    }
    const emojis = emojiResult.value && typeof emojiResult.value === "object"
      ? emojiResult.value
      : {};
    const descriptions = descriptionsResult.status === "fulfilled" &&
      descriptionsResult.value && typeof descriptionsResult.value === "object"
      ? descriptionsResult.value
      : {};
    window.MemeManagerUI.state.latestEmojiData = emojis;
    window.MemeManagerUI.state.latestTagDescriptions = descriptions;
    window.MemeManagerUI.emoji.displayCategories(emojis, descriptions);
    window.MemeManagerUI.emoji.updateSidebar(emojis);
  } catch (error) {
    window.MemeManagerUI.state.error = error?.message || String(error);
    window.MemeManagerUI.state.latestEmojiData = {};
    window.MemeManagerUI.state.latestTagDescriptions = {};
    window.MemeManagerUI.emoji.displayCategories({}, {});
    window.MemeManagerUI.emoji.updateSidebar({});
    window.MemeManagerUI.dialogs.showToast(
      error?.message || String(error),
      "error",
      "加载失败",
    );
  } finally {
    window.MemeManagerUI.state.loading = false;
  }
};

window.MemeManagerUI.emoji.refreshUi = async function ({
  emojis = false,
  syncStatus = false,
} = {}) {
  if (emojis) {
    await Promise.all([
      window.MemeManagerUI.emoji.fetchEmojis(),
      window.MemeManagerUI.pack.refreshManagePackSummaries(),
    ]);
  }
  if (syncStatus) await window.MemeManagerUI.pack.checkSyncStatus(false);
};

window.MemeManagerUI.emoji.isCompactViewport = function () {
  return window.matchMedia(window.MemeManagerUI.state.MOBILE_LAYOUT_MEDIA).matches;
};

window.MemeManagerUI.emoji.isConsoleVisible = function () {
  return !window.MemeManagerUI.state.leftPanel?.classList.contains("panel-collapsed");
};

window.MemeManagerUI.emoji.isDirectoryVisible = function () {
  return !window.MemeManagerUI.state.directoryPanel?.classList.contains("panel-collapsed");
};

window.MemeManagerUI.emoji.setConsoleVisible = function (visible) {
  window.MemeManagerUI.state.leftPanel?.classList.toggle("panel-collapsed", !visible);
};

window.MemeManagerUI.emoji.setDirectoryVisible = function (visible) {
  window.MemeManagerUI.state.directoryPanel?.classList.toggle("panel-collapsed", !visible);
};

window.MemeManagerUI.emoji.closeAllPanels = function () {
  window.MemeManagerUI.emoji.setConsoleVisible(false);
  window.MemeManagerUI.emoji.setDirectoryVisible(false);
};

window.MemeManagerUI.emoji.updatePanelToggleState = function () {
  const consoleVisible = window.MemeManagerUI.emoji.isConsoleVisible();
  const directoryVisible = window.MemeManagerUI.emoji.isDirectoryVisible();
  window.MemeManagerUI.state.consoleToggleBtn?.setAttribute("aria-expanded", String(consoleVisible));
  window.MemeManagerUI.state.directoryToggleBtn?.setAttribute("aria-expanded", String(directoryVisible));
  const showBackdrop = window.MemeManagerUI.emoji.isCompactViewport() &&
    (consoleVisible || directoryVisible);
  window.MemeManagerUI.state.sidebarBackdrop?.classList.toggle("hidden", !showBackdrop);
  window.MemeManagerUI.state.sidebarBackdrop?.setAttribute(
    "aria-hidden",
    String(!showBackdrop),
  );
};

window.MemeManagerUI.emoji.syncSidebarLayout = function () {
  if (window.MemeManagerUI.emoji.isCompactViewport()) {
    window.MemeManagerUI.emoji.closeAllPanels();
  } else {
    window.MemeManagerUI.emoji.setConsoleVisible(true);
    window.MemeManagerUI.emoji.setDirectoryVisible(true);
  }
  window.MemeManagerUI.emoji.updatePanelToggleState();
};

window.MemeManagerUI.emoji.toggleConsolePanel = function () {
  window.MemeManagerUI.emoji.setConsoleVisible(
    !window.MemeManagerUI.emoji.isConsoleVisible(),
  );
  window.MemeManagerUI.emoji.updatePanelToggleState();
};

window.MemeManagerUI.emoji.toggleDirectoryPanel = function () {
  window.MemeManagerUI.emoji.setDirectoryVisible(
    !window.MemeManagerUI.emoji.isDirectoryVisible(),
  );
  window.MemeManagerUI.emoji.updatePanelToggleState();
};

window.MemeManagerUI.emoji.getImageRequestParams = function (
  category,
  emoji,
  size = "preview",
) {
  return { category, filename: emoji, size };
};

window.MemeManagerUI.emoji.loadPreviewImage = async function (
  category,
  emoji,
  size = "preview",
) {
  const data = await window.MemeManagerUI.api.apiGet(
    "meme_image_data",
    window.MemeManagerUI.emoji.getImageRequestParams(category, emoji, size),
  );
  if (!data?.data_url) throw new Error("图片接口未返回预览数据");
  return data.data_url;
};

window.MemeManagerUI.emoji.loadEmojiPreview = async function (item) {
  if (!item || item.dataset.loading === "true" || item.dataset.previewDataUrl) return;
  item.dataset.loading = "true";
  item.classList.add("emoji-loading");
  try {
    const dataUrl = await window.MemeManagerUI.emoji.loadPreviewImage(
      item.dataset.category,
      item.dataset.emoji,
      "preview",
    );
    item.dataset.previewDataUrl = dataUrl;
    item.style.backgroundImage = `url("${dataUrl}")`;
    item.classList.remove("emoji-loading", "emoji-load-error");
    item.classList.add("emoji-loaded");
  } catch (error) {
    item.classList.remove("emoji-loading", "emoji-loaded");
    item.classList.add("emoji-load-error");
    item.setAttribute("aria-label", "预览加载失败，点击重试");
  } finally {
    item.dataset.loading = "false";
  }
};

window.MemeManagerUI.emoji.setImagePreviewBusy = function (busy) {
  window.MemeManagerUI.state.imagePreviewLoading?.classList.toggle("hidden", !busy);
  if (window.MemeManagerUI.state.imagePreviewOriginalBtn) {
    window.MemeManagerUI.state.imagePreviewOriginalBtn.disabled = busy;
  }
};

window.MemeManagerUI.emoji.closeImagePreview = function () {
  window.MemeManagerUI.state.imagePreviewState = null;
  window.MemeManagerUI.state.imagePreviewModalRoot?.classList.add("hidden");
  window.MemeManagerUI.state.imagePreviewModalRoot?.setAttribute("aria-hidden", "true");
  window.MemeManagerUI.state.imagePreviewImg?.removeAttribute("src");
  window.MemeManagerUI.emoji.setImagePreviewBusy(false);
};

window.MemeManagerUI.emoji.openImagePreview = async function (
  category,
  emoji,
  previewDataUrl = "",
) {
  if (!window.MemeManagerUI.state.imagePreviewModalRoot ||
      !window.MemeManagerUI.state.imagePreviewImg) return;
  window.MemeManagerUI.state.imagePreviewState = { category, emoji };
  window.MemeManagerUI.state.imagePreviewModalRoot.classList.remove("hidden");
  window.MemeManagerUI.state.imagePreviewModalRoot.setAttribute("aria-hidden", "false");
  window.MemeManagerUI.state.imagePreviewImg.alt = `表情包预览：${emoji}`;
  if (previewDataUrl) window.MemeManagerUI.state.imagePreviewImg.src = previewDataUrl;
  window.MemeManagerUI.emoji.setImagePreviewBusy(!previewDataUrl);
  if (previewDataUrl) return;

  const previewRequest = window.MemeManagerUI.emoji.loadPreviewImage(category, emoji);
  const [previewResult] = await Promise.allSettled([previewRequest]);
  if (previewResult.status === "rejected") {
    window.MemeManagerUI.dialogs.showToast(
      previewResult.reason?.message || "预览加载失败",
      "error",
      "预览失败",
    );
  } else if (window.MemeManagerUI.state.imagePreviewState?.emoji === emoji) {
    window.MemeManagerUI.state.imagePreviewImg.src = previewResult.value;
  }
  window.MemeManagerUI.emoji.setImagePreviewBusy(false);
};

window.MemeManagerUI.emoji.showOriginalPreview = async function () {
  const state = window.MemeManagerUI.state.imagePreviewState;
  if (!state) return;
  window.MemeManagerUI.emoji.setImagePreviewBusy(true);
  try {
    window.MemeManagerUI.state.imagePreviewImg.src =
      await window.MemeManagerUI.emoji.loadPreviewImage(
        state.category,
        state.emoji,
        "original",
      );
  } catch (error) {
    window.MemeManagerUI.dialogs.showToast(
      error?.message || String(error),
      "error",
      "原图加载失败",
    );
  } finally {
    window.MemeManagerUI.emoji.setImagePreviewBusy(false);
  }
};

window.MemeManagerUI.emoji.uploadEmoji = async function (category, file) {
  const managedPackId = window.MemeManagerUI.api.getSelectedPackId();
  const query = managedPackId
    ? `?managed_pack_id=${encodeURIComponent(managedPackId)}`
    : "";
  return window.AstrBotPluginPage.upload(
    `emoji/add/${encodeURIComponent(category)}${query}`,
    file,
  );
};

window.MemeManagerUI.emoji.uploadFile = async function (category, file, button) {
  if (!file) return;
  window.MemeManagerUI.emoji.setButtonBusy(button, "上传中...");
  try {
    await window.MemeManagerUI.emoji.uploadEmoji(category, file);
    await window.MemeManagerUI.emoji.refreshUi({ emojis: true });
    window.MemeManagerUI.dialogs.showToast("图片已上传。", "success", "上传成功");
  } catch (error) {
    window.MemeManagerUI.dialogs.showToast(
      error?.message || String(error),
      "error",
      "上传失败",
    );
  } finally {
    window.MemeManagerUI.emoji.restoreButton(button);
  }
};

window.MemeManagerUI.emoji.deleteEmoji = async function (category, emoji) {
  const confirmed = await window.MemeManagerUI.dialogs.showConfirm({
    title: "删除表情包",
    description: `确认删除分类「${category}」中的表情包「${emoji}」？此操作不可恢复。`,
    confirmLabel: "确认删除",
    confirmClassName: "danger",
  });
  if (!confirmed) return;
  try {
    await window.MemeManagerUI.api.apiPost("emoji/delete", {
      category,
      image_file: emoji,
    });
    await window.MemeManagerUI.emoji.refreshUi({ emojis: true });
    window.MemeManagerUI.dialogs.showToast("表情包已删除。", "success", "删除成功");
  } catch (error) {
    window.MemeManagerUI.dialogs.showToast(
      error?.message || String(error),
      "error",
      "删除失败",
    );
  }
};

window.MemeManagerUI.emoji.moveEmoji = async function (
  sourceCategory,
  emoji,
  targetCategory,
) {
  if (!targetCategory || sourceCategory === targetCategory) return;
  const confirmed = await window.MemeManagerUI.dialogs.showConfirm({
    title: "移动表情包",
    description: `将「${emoji}」从「${sourceCategory}」移动到「${targetCategory}」？`,
    confirmLabel: "确认移动",
  });
  if (!confirmed) return;
  try {
    const data = await window.MemeManagerUI.api.apiPost("emoji/batch_move", {
      source_category: sourceCategory,
      target_category: targetCategory,
      image_files: [emoji],
    });
    if (!Number(data?.moved_count || 0)) {
      throw new Error(data?.message || "表情包未能移动");
    }
    await window.MemeManagerUI.emoji.refreshUi({ emojis: true });
    window.MemeManagerUI.dialogs.showToast("表情包已移动。", "success", "移动成功");
  } catch (error) {
    window.MemeManagerUI.dialogs.showToast(
      error?.message || String(error),
      "error",
      "移动失败",
    );
  }
};

window.MemeManagerUI.emoji.createUploadControl = function (category) {
  const wrapper = document.createElement("div");
  wrapper.className = "emoji-upload";
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/*";
  input.hidden = true;
  const button = window.MemeManagerUI.emoji.createButton({
    className: "upload-emoji",
    text: "上传图片",
    onClick: () => input.click(),
  });
  input.addEventListener("change", () => {
    void window.MemeManagerUI.emoji.uploadFile(category, input.files?.[0], button);
    input.value = "";
  });
  wrapper.append(button, input);
  return wrapper;
};

window.MemeManagerUI.emoji.createEmojiItem = function (category, emoji, categories) {
  const item = document.createElement("article");
  item.className = "emoji-item";
  item.dataset.category = category;
  item.dataset.emoji = emoji;
  item.dataset.loading = "false";
  item.tabIndex = 0;
  item.setAttribute("aria-label", `预览表情包 ${emoji}`);

  const actions = document.createElement("div");
  actions.className = "emoji-item-actions";
  const moveSelect = document.createElement("select");
  moveSelect.className = "emoji-move-select";
  moveSelect.setAttribute("aria-label", `移动 ${emoji} 到其他分类`);
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "移动到…";
  moveSelect.append(placeholder);
  categories.filter((name) => name !== category).forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    moveSelect.append(option);
  });
  moveSelect.addEventListener("click", (event) => event.stopPropagation());
  moveSelect.addEventListener("change", (event) => {
    event.stopPropagation();
    const target = moveSelect.value;
    moveSelect.value = "";
    void window.MemeManagerUI.emoji.moveEmoji(category, emoji, target);
  });

  const deleteButton = window.MemeManagerUI.emoji.createButton({
    className: "delete-btn",
    text: "×",
    onClick: (event) => {
      event.stopPropagation();
      void window.MemeManagerUI.emoji.deleteEmoji(category, emoji);
    },
  });
  deleteButton.setAttribute("aria-label", `删除 ${emoji}`);
  actions.append(moveSelect, deleteButton);
  item.append(actions);

  const openPreview = () => {
    if (item.classList.contains("emoji-load-error")) {
      item.classList.remove("emoji-load-error");
      delete item.dataset.previewDataUrl;
      void window.MemeManagerUI.emoji.loadEmojiPreview(item);
      return;
    }
    void window.MemeManagerUI.emoji.openImagePreview(
      category,
      emoji,
      item.dataset.previewDataUrl || "",
    );
  };
  item.addEventListener("click", openPreview);
  item.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openPreview();
    }
  });
  return item;
};

window.MemeManagerUI.emoji.displayCategories = function (emojiData, descriptions) {
  const container = document.getElementById("emoji-categories");
  if (!container) return;
  container.replaceChildren();
  const categories = Object.keys(emojiData || {});
  const total = categories.reduce(
    (count, category) => count + (Array.isArray(emojiData[category]) ? emojiData[category].length : 0),
    0,
  );

  if (!total) {
    const hint = document.createElement("div");
    hint.className = "empty-pack-hint";
    const title = document.createElement("p");
    title.className = "empty-pack-hint-title";
    title.textContent = "当前还没有表情包内容";
    const copy = document.createElement("p");
    copy.className = "empty-pack-hint-meta";
    copy.textContent = "请前往设置中心导入表情包，或在下方固定分类中上传图片。";
    const link = document.createElement("a");
    link.href = "#settings";
    link.textContent = "前往设置中心";
    link.className = "empty-pack-settings-link";
    hint.append(title, copy, link);
    container.append(hint);
  }

  categories.forEach((category) => {
    const categoryElement = document.createElement("section");
    categoryElement.className = "category";
    categoryElement.id = `category-${category}`;
    const header = document.createElement("div");
    header.className = "category-title";
    const titleRow = document.createElement("div");
    titleRow.className = "category-header";
    const title = document.createElement("h2");
    title.textContent = category;
    const edit = window.MemeManagerUI.emoji.createButton({
      className: "edit-category-btn",
      text: "编辑描述",
      onClick: () => window.MemeManagerUI.emoji.editCategory(category),
    });
    titleRow.append(title, edit);
    const description = document.createElement("p");
    description.className = "description";
    description.id = `category-desc-${category}`;
    description.textContent = descriptions?.[category] || "请添加描述";
    header.append(titleRow, description);

    const grid = document.createElement("div");
    grid.className = "emoji-grid";
    (Array.isArray(emojiData[category]) ? emojiData[category] : []).forEach((emoji) => {
      const item = window.MemeManagerUI.emoji.createEmojiItem(category, emoji, categories);
      grid.append(item);
      void window.MemeManagerUI.emoji.loadEmojiPreview(item);
    });
    grid.append(window.MemeManagerUI.emoji.createUploadControl(category));
    categoryElement.append(header, grid);
    container.append(categoryElement);
  });
};

window.MemeManagerUI.emoji.updateSidebar = function (emojiData) {
  const list = document.getElementById("sidebar-list");
  if (!list) return;
  list.replaceChildren();
  Object.keys(emojiData || {}).forEach((category) => {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = `#category-${category}`;
    link.textContent = category;
    link.addEventListener("click", (event) => {
      event.preventDefault();
      document.getElementById(`category-${category}`)?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
    item.append(link);
    list.append(item);
  });
};

window.MemeManagerUI.emoji.closeCategoryEditModal = function () {
  window.MemeManagerUI.state.categoryEditModalRoot?.classList.add("hidden");
  window.MemeManagerUI.state.categoryEditModalRoot?.setAttribute("aria-hidden", "true");
  window.MemeManagerUI.state.activeCategoryEdit = null;
};

window.MemeManagerUI.emoji.editCategory = function (category) {
  window.MemeManagerUI.state.activeCategoryEdit = category;
  window.MemeManagerUI.state.categoryEditModalTitle.textContent = `编辑类别「${category}」`;
  window.MemeManagerUI.state.categoryEditModalDescription.textContent =
    "仅可修改标签描述，标签名称保持固定。";
  window.MemeManagerUI.state.categoryEditNameInput.value = category;
  const current = document.getElementById(`category-desc-${category}`)?.textContent?.trim();
  window.MemeManagerUI.state.categoryEditDescInput.value =
    current && current !== "请添加描述" ? current : "";
  window.MemeManagerUI.state.categoryEditModalRoot.classList.remove("hidden");
  window.MemeManagerUI.state.categoryEditModalRoot.setAttribute("aria-hidden", "false");
  window.MemeManagerUI.state.categoryEditDescInput.focus();
};

window.MemeManagerUI.emoji.cancelEdit = window.MemeManagerUI.emoji.closeCategoryEditModal;

window.MemeManagerUI.emoji.saveCategory = async function () {
  const tag = window.MemeManagerUI.state.activeCategoryEdit;
  if (!tag) return;
  window.MemeManagerUI.emoji.setButtonBusy(
    window.MemeManagerUI.state.categoryEditSaveBtn,
    "保存中...",
  );
  try {
    await window.MemeManagerUI.api.apiPost("category/update_description", {
      tag,
      description: window.MemeManagerUI.state.categoryEditDescInput.value.trim(),
    });
    await window.MemeManagerUI.emoji.refreshUi({ emojis: true, syncStatus: true });
    window.MemeManagerUI.emoji.closeCategoryEditModal();
    window.MemeManagerUI.dialogs.showToast("分类描述已保存。", "success", "保存成功");
  } catch (error) {
    window.MemeManagerUI.dialogs.showToast(
      error?.message || String(error),
      "error",
      "保存失败",
    );
  } finally {
    window.MemeManagerUI.emoji.restoreButton(window.MemeManagerUI.state.categoryEditSaveBtn);
  }
};
