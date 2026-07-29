const initCaptureIndexPage = async () => {
  const pageApi = window.AstrBotPluginPage;
  const packSelect = document.querySelector("#pack");
  const captureSummary = document.querySelector("#capture-summary");
  const captureFolders = document.querySelector("#capture-folders");
  const captureIndexedItems = document.querySelector("#capture-indexed-items");
  const capturePendingItems = document.querySelector("#capture-pending-items");
  const captureIndexedCount = document.querySelector("#capture-indexed-count");
  const capturePendingCount = document.querySelector("#capture-pending-count");
  const captureIndexButton = document.querySelector("#capture-index-button");
  const captureRefreshButton = document.querySelector("#capture-refresh-button");
  const notice = document.querySelector("#notice");
  const dialogMask = document.querySelector("#dialog-mask");
  const dialogTitle = document.querySelector("#dialog-title");
  const dialogMessage = document.querySelector("#dialog-message");
  const dialogCancel = document.querySelector("#dialog-cancel");
  const dialogConfirm = document.querySelector("#dialog-confirm");
  const toastContainer = document.querySelector("#toast-container");
  const imagePreviewMask = document.querySelector("#image-preview-mask");
  const imagePreviewTitle = document.querySelector("#image-preview-title");
  const imagePreviewClose = document.querySelector("#image-preview-close");
  const imagePreviewImg = document.querySelector("#image-preview-img");
  const imagePreviewLoading = document.querySelector("#image-preview-loading");
  const previewCache = new Map();
  const previewRequests = new Map();
  const previewQueue = [];
  let activePreviewRequests = 0;
  let dialogResolver = null;
  let captureIndexSubmitting = false;
  let toastTimer = null;

  if (!pageApi) {
    notice.textContent = "请从 AstrBot WebUI 的“表情索引”入口打开此页面。";
    notice.classList.add("error");
    return;
  }

  const apiGet = (path, params = {}) => pageApi.apiGet(path, params);
  const apiPost = (path, body = {}) => pageApi.apiPost(path, body);

  const errorMessage = (error) =>
    String(error?.message || error || "操作失败，请查看日志后重试");

  const showToast = (message, isError = false) => {
    toastContainer.replaceChildren();
    const toast = document.createElement("div");
    toast.className = `toast${isError ? " error" : ""}`;
    toast.textContent = String(message || "");
    toastContainer.append(toast);
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toastContainer.replaceChildren(), 4200);
  };

  const showNotice = (message, isError = false) => {
    notice.textContent = String(message || "");
    notice.classList.toggle("error", isError);
  };

  const setDialog = (open, title = "", message = "", confirmText = "确定") => {
    dialogTitle.textContent = title;
    dialogMessage.textContent = message;
    dialogConfirm.textContent = confirmText;
    dialogMask.classList.toggle("hidden", !open);
    dialogMask.setAttribute("aria-hidden", open ? "false" : "true");
  };

  const closeDialog = (value) => {
    setDialog(false);
    const resolver = dialogResolver;
    dialogResolver = null;
    if (resolver) resolver(value);
  };

  const confirmAction = (title, message) =>
    new Promise((resolve) => {
      dialogResolver = resolve;
      setDialog(true, title, message, "开始处理");
    });

  const imageLocation = (item) => {
    const parts = String(item?.relative_path || "")
      .replace(/\\/g, "/")
      .split("/")
      .filter(Boolean);
    if (parts[0] === "memes") parts.shift();
    const filename = parts.pop() || "";
    return { category: parts.join("/"), filename };
  };

  const previewKey = (item) =>
    `${packSelect.value}:${String(item?.relative_path || "")}`;

  const pumpPreviewQueue = () => {
    while (activePreviewRequests < 4 && previewQueue.length) {
      const job = previewQueue.shift();
      activePreviewRequests += 1;
      Promise.resolve()
        .then(job.task)
        .then(job.resolve, job.reject)
        .finally(() => {
          activePreviewRequests -= 1;
          pumpPreviewQueue();
        });
    }
  };

  const schedulePreviewRequest = (task, priority = false) =>
    new Promise((resolve, reject) => {
      const job = { task, resolve, reject };
      if (priority) previewQueue.unshift(job);
      else previewQueue.push(job);
      pumpPreviewQueue();
    });

  const loadImage = async (item, size = "preview") => {
    const key = `${previewKey(item)}:${size}`;
    if (size === "preview" && previewCache.has(key)) return previewCache.get(key);
    if (previewRequests.has(key)) return previewRequests.get(key);
    const { category, filename } = imageLocation(item);
    if (!category || !filename) throw new Error("图片路径不可用");
    const promise = schedulePreviewRequest(
      () =>
        apiGet("meme_image_data", {
          managed_pack_id: packSelect.value,
          category,
          filename,
          size,
        }),
      size === "original",
    )
      .then((data) => {
        if (!data?.data_url) throw new Error("图片接口未返回预览数据");
        if (size === "preview") previewCache.set(key, data.data_url);
        return data.data_url;
      })
      .finally(() => previewRequests.delete(key));
    previewRequests.set(key, promise);
    return promise;
  };

  const openImagePreview = async (item, previewDataUrl = "") => {
    const key = previewKey(item);
    imagePreviewTitle.textContent = item.relative_path || "表情包预览";
    imagePreviewMask.classList.remove("hidden");
    imagePreviewMask.setAttribute("aria-hidden", "false");
    imagePreviewLoading.textContent = "正在加载大图……";
    imagePreviewLoading.classList.remove("hidden");
    imagePreviewImg.src = previewDataUrl;
    try {
      const original = await loadImage(item, "original");
      if (previewKey(item) !== key) return;
      imagePreviewImg.src = original;
      imagePreviewLoading.classList.add("hidden");
    } catch (_) {
      imagePreviewLoading.textContent = "大图加载失败，已保留缩略图";
    }
  };

  const closeImagePreview = () => {
    imagePreviewMask.classList.add("hidden");
    imagePreviewMask.setAttribute("aria-hidden", "true");
    imagePreviewImg.removeAttribute("src");
  };

  const renderEmpty = (container, message) => {
    container.replaceChildren();
    const empty = document.createElement("div");
    empty.className = "capture-empty";
    empty.textContent = message;
    container.append(empty);
  };

  const renderCard = (item, container) => {
    const card = document.createElement("article");
    card.className = `capture-card${item.duplicate ? " is-duplicate" : ""}`;
    const preview = document.createElement("button");
    preview.type = "button";
    preview.className = "capture-card-preview";
    const image = document.createElement("img");
    image.alt = `表情包预览：${item.filename || ""}`;
    const loading = document.createElement("span");
    loading.textContent = "加载预览";
    preview.append(loading);
    void loadImage(item)
      .then((dataUrl) => {
        if (!preview.isConnected) return;
        image.src = dataUrl;
        preview.replaceChildren(image);
      })
      .catch(() => {
        if (preview.isConnected) loading.textContent = "预览失败";
      });
    preview.addEventListener("click", () =>
      openImagePreview(item, image.src || ""),
    );

    const body = document.createElement("div");
    body.className = "capture-card-body";
    const meta = document.createElement("div");
    meta.className = "capture-card-meta";
    const category = document.createElement("span");
    category.className = "capture-category";
    category.textContent = item.category || "未分类";
    const status = document.createElement("span");
    status.className = `capture-status${item.duplicate ? " duplicate" : ""}`;
    status.textContent = item.duplicate ? "重复待去重" : item.indexed ? "已索引" : "待分类";
    meta.append(category, status);
    const filename = document.createElement("h4");
    filename.textContent = item.filename || "未命名图片";
    const description = document.createElement("p");
    description.className = "capture-description";
    description.textContent = item.description || "暂无描述，等待分类索引";
    const detail = document.createElement("p");
    detail.className = "capture-detail";
    const tags = Array.isArray(item.tags) ? item.tags.filter(Boolean).join("、") : "";
    detail.textContent = [item.emotion, tags ? `标签：${tags}` : ""]
      .filter(Boolean)
      .join(" · ") || (item.duplicate_of ? `已有文件：${item.duplicate_of}` : "等待处理");
    body.append(meta, filename, description, detail);
    card.append(preview, body);
    container.append(card);
  };

  const renderWorkspace = (data) => {
    const summary = data?.summary || {};
    const state = data?.library_index || {};
    captureSummary.replaceChildren();
    [
      ["已索引", summary.indexed || 0, "cool"],
      ["待分类", summary.pending || 0, "warm"],
      ["重复待去重", summary.duplicate || 0, "warm"],
      ["已完成文件夹", `${summary.complete_folders || 0} / ${summary.folder_total || 0}`, "cool"],
    ].forEach(([label, value, tone]) => {
      const stat = document.createElement("div");
      stat.className = `capture-stat ${tone}`;
      stat.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
      captureSummary.append(stat);
    });
    const stateNote = document.createElement("p");
    stateNote.className = "capture-state-note";
    stateNote.textContent = state.message || "目录索引尚未运行";
    captureSummary.append(stateNote);

    captureFolders.replaceChildren();
    (data?.folders || []).forEach((folder) => {
      const chip = document.createElement("span");
      chip.className = `capture-folder-chip${folder.complete ? " complete" : ""}`;
      chip.textContent = `${folder.category} · ${folder.indexed}/${folder.total}`;
      chip.title = folder.complete ? "已完成，不会重复调用模型" : `待分类 ${folder.pending || 0} 张`;
      captureFolders.append(chip);
    });
    if (!captureFolders.children.length) {
      const empty = document.createElement("span");
      empty.className = "capture-folder-empty";
      empty.textContent = "还没有可展示的偷取分类目录";
      captureFolders.append(empty);
    }

    const indexed = Array.isArray(data?.indexed_items) ? data.indexed_items : [];
    const pending = Array.isArray(data?.pending_items) ? data.pending_items : [];
    captureIndexedCount.textContent = `${summary.indexed || 0} 张`;
    capturePendingCount.textContent = `${(summary.pending || 0) + (summary.duplicate || 0)} 条`;
    if (indexed.length) {
      captureIndexedItems.replaceChildren();
      indexed.forEach((item) => renderCard(item, captureIndexedItems));
    } else renderEmpty(captureIndexedItems, "暂无已完成的偷取索引");
    if (pending.length) {
      capturePendingItems.replaceChildren();
      pending.forEach((item) => renderCard(item, capturePendingItems));
    } else renderEmpty(capturePendingItems, "当前没有待处理偷取图片");
    captureIndexButton.disabled =
      captureIndexSubmitting ||
      state.status === "running" ||
      !state.active_pack ||
      !(summary.pending || summary.duplicate);
    captureRefreshButton.disabled = captureIndexSubmitting;
  };

  const loadWorkspace = async () => {
    if (!packSelect.value) return;
    try {
      renderWorkspace(await apiGet("semantic/capture-workspace", { pack_id: packSelect.value }));
    } catch (error) {
      showNotice(errorMessage(error), true);
    }
  };

  const loadPacks = async () => {
    const data = await apiGet("packs");
    packSelect.replaceChildren();
    (data?.packs || []).forEach((pack) => {
      const option = document.createElement("option");
      option.value = String(pack.id || "");
      option.textContent = pack.name || pack.id || "未命名资源包";
      packSelect.append(option);
    });
  };

  const applySecureNavLinks = async () => {
    let token = "";
    try {
      token = String((await apiGet("bridge/auth_token"))?.token || "").trim();
    } catch (_) {}
    document.querySelectorAll("a[data-nav-target]").forEach((link) => {
      const target = link.getAttribute("data-nav-target");
      if (!target) return;
      const url = new URL(target, window.location.href);
      const current = new URLSearchParams(window.location.search);
      current.forEach((value, key) => {
        if (key !== "asset_token" && !url.searchParams.has(key)) url.searchParams.set(key, value);
      });
      if (token) url.searchParams.set("asset_token", token);
      link.href = url.toString();
    });
  };

  dialogCancel.addEventListener("click", () => closeDialog(false));
  dialogConfirm.addEventListener("click", () => closeDialog(true));
  dialogMask.addEventListener("click", (event) => {
    if (event.target === dialogMask) closeDialog(false);
  });
  imagePreviewClose.addEventListener("click", closeImagePreview);
  imagePreviewMask.addEventListener("click", (event) => {
    if (event.target === imagePreviewMask) closeImagePreview();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeDialog(false);
      closeImagePreview();
    }
  });
  captureRefreshButton.addEventListener("click", loadWorkspace);
  packSelect.addEventListener("change", loadWorkspace);
  captureIndexButton.addEventListener("click", async () => {
    if (!packSelect.value || captureIndexSubmitting) return;
    const confirmed = await confirmAction(
      "开始分类索引",
      "只处理当前资源包中待分类图片；已完成文件夹会跳过，重复记录会在此阶段去重。",
    );
    if (!confirmed) return;
    captureIndexSubmitting = true;
    captureIndexButton.disabled = true;
    showNotice("正在提交分类索引……");
    try {
      const result = await apiPost("semantic/capture-index", { pack_id: packSelect.value });
      showToast(result?.message || "分类索引已开始");
      showNotice(result?.message || "分类索引已开始");
    } catch (error) {
      showToast(errorMessage(error), true);
      showNotice(errorMessage(error), true);
    } finally {
      captureIndexSubmitting = false;
      await loadWorkspace();
    }
  });

  await pageApi.ready();
  await applySecureNavLinks();
  await loadPacks();
  await loadWorkspace();
  window.setInterval(() => loadWorkspace(), 5000);
};

initCaptureIndexPage().catch((error) => {
  const notice = document.querySelector("#notice");
  if (notice) {
    notice.textContent = error?.message || String(error);
    notice.classList.add("error");
  }
});
