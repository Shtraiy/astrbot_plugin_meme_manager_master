window.MemeManagerUI = window.MemeManagerUI || {};
window.MemeManagerUI.pack = window.MemeManagerUI.pack || {};

window.MemeManagerUI.pack.formatPackOptionLabel = function (pack) {
  const packName = String(pack?.name || pack?.id || "未命名");
  const count = Number(pack?.image_count || 0);
  return `${packName} (${count} 张)`;
};

window.MemeManagerUI.pack.syncManagedPackQuery = function (managedPackId) {
  const normalized = String(managedPackId || "").trim();
  window.MemeManagerUI.state.managedPackIdFromUrl = normalized;
  window.MemeManagerUI.router?.updateManagedPackQuery(normalized);
};

window.MemeManagerUI.pack.refreshManagePackSummaries = async function () {
  try {
    const response = await window.MemeManagerUI.api.apiGet("packs");
    const packs = Array.isArray(response?.packs) ? response.packs : [];
    window.MemeManagerUI.state.managePacksById = new Map(
      packs.map((pack) => [String(pack?.id || "").trim(), pack]),
    );
    Array.from(window.MemeManagerUI.state.managePackSelect?.options || []).forEach((option) => {
      const pack = window.MemeManagerUI.state.managePacksById.get(String(option.value || "").trim());
      if (pack) option.textContent = window.MemeManagerUI.pack.formatPackOptionLabel(pack);
    });
    return packs;
  } catch (error) {
    console.warn("刷新表情包摘要失败:", error);
    return [];
  }
};

window.MemeManagerUI.pack.loadManagePackSwitcher = async function (preferredPackId = "") {
  const select = window.MemeManagerUI.state.managePackSelect;
  if (!select) return [];

  try {
    const response = await window.MemeManagerUI.api.apiGet("packs");
    const packs = Array.isArray(response?.packs) ? response.packs : [];
    window.MemeManagerUI.state.managePacksById = new Map(
      packs.map((pack) => [String(pack?.id || "").trim(), pack]),
    );
    select.replaceChildren();

    if (!packs.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "暂无可用表情包";
      select.append(option);
      select.disabled = true;
      window.MemeManagerUI.state.activeManagePackId = "";
      window.MemeManagerUI.state.switchManagePackBtn.disabled = true;
      window.MemeManagerUI.state.deleteManagePackBtn.disabled = true;
      window.MemeManagerUI.pack.syncManagedPackQuery("");
      return packs;
    }

    let firstPackId = "";
    let defaultPackId = "";
    packs.forEach((pack) => {
      const option = document.createElement("option");
      option.value = String(pack?.id || "").trim();
      option.textContent = window.MemeManagerUI.pack.formatPackOptionLabel(pack);
      select.append(option);
      if (!firstPackId) firstPackId = option.value;
      if (!defaultPackId && pack?.is_default) defaultPackId = option.value;
    });

    const availableIds = new Set(packs.map((pack) => String(pack?.id || "").trim()));
    const candidates = [
      preferredPackId,
      window.MemeManagerUI.state.managedPackIdFromUrl,
      defaultPackId,
      firstPackId,
    ].map((value) => String(value || "").trim());
    const selectedPackId = candidates.find((packId) => availableIds.has(packId)) || firstPackId;

    select.disabled = false;
    select.value = selectedPackId;
    window.MemeManagerUI.state.defaultManagePackId = defaultPackId || firstPackId;
    window.MemeManagerUI.state.activeManagePackId = selectedPackId;
    window.MemeManagerUI.state.switchManagePackBtn.disabled = false;
    window.MemeManagerUI.state.deleteManagePackBtn.disabled = false;
    window.MemeManagerUI.pack.syncManagedPackQuery(selectedPackId);
    return packs;
  } catch (error) {
    window.MemeManagerUI.dialogs.showToast(
      error?.message || String(error),
      "error",
      "加载表情包失败",
    );
    return [];
  }
};

window.MemeManagerUI.pack.switchManagePack = async function () {
  const targetPackId = String(
    window.MemeManagerUI.state.managePackSelect?.value || "",
  ).trim();
  if (!targetPackId) {
    window.MemeManagerUI.dialogs.showToast("请先选择表情包。", "warning", "切换失败");
    return;
  }

  const previousPackId = window.MemeManagerUI.state.activeManagePackId;
  window.MemeManagerUI.emoji.setButtonBusy(
    window.MemeManagerUI.state.switchManagePackBtn,
    "切换中...",
  );
  window.MemeManagerUI.emoji.closeImagePreview();
  window.MemeManagerUI.state.activeManagePackId = targetPackId;
  window.MemeManagerUI.pack.syncManagedPackQuery(targetPackId);
  try {
    await window.MemeManagerUI.emoji.refreshUi({ emojis: true, syncStatus: true });
    window.MemeManagerUI.dialogs.showToast(
      `已切换管理视图到 ${targetPackId}。`,
      "success",
      "切换成功",
    );
  } catch (error) {
    window.MemeManagerUI.state.activeManagePackId = previousPackId;
    window.MemeManagerUI.pack.syncManagedPackQuery(previousPackId);
    window.MemeManagerUI.dialogs.showToast(
      error?.message || String(error),
      "error",
      "切换失败",
    );
  } finally {
    window.MemeManagerUI.emoji.restoreButton(window.MemeManagerUI.state.switchManagePackBtn);
  }
};

window.MemeManagerUI.pack.deleteCurrentManagePack = async function () {
  const targetPackId = String(
    window.MemeManagerUI.state.activeManagePackId ||
      window.MemeManagerUI.state.managePackSelect?.value ||
      "",
  ).trim();
  if (!targetPackId) {
    window.MemeManagerUI.dialogs.showToast(
      "请先选择要删除的表情包。",
      "warning",
      "删除失败",
    );
    return;
  }

  const confirmed = await window.MemeManagerUI.dialogs.showDangerConfirm({
    title: `删除表情包组「${targetPackId}」`,
    description: "该操作会删除整个表情包组，包括分类与图片；删除后会自动切换到可用表情包。",
    actionLabel: "确认删除当前表情包组",
    countdown: 5,
  });
  if (!confirmed) return;

  window.MemeManagerUI.emoji.setButtonBusy(
    window.MemeManagerUI.state.deleteManagePackBtn,
    "删除中...",
  );
  try {
    const data = await window.MemeManagerUI.api.apiPost("packs/uninstall", {
      pack_id: targetPackId,
    });
    const switchedPackId = String(data?.switched_default_to || "").trim();
    await window.MemeManagerUI.pack.loadManagePackSwitcher(switchedPackId);
    await window.MemeManagerUI.emoji.refreshUi({ emojis: true, syncStatus: true });
    window.MemeManagerUI.dialogs.showToast(
      `已删除 ${targetPackId}${switchedPackId ? `，已切换到 ${switchedPackId}` : ""}`,
      "success",
      "删除成功",
    );
  } catch (error) {
    window.MemeManagerUI.dialogs.showToast(
      error?.message || String(error),
      "error",
      "删除失败",
    );
  } finally {
    window.MemeManagerUI.emoji.restoreButton(window.MemeManagerUI.state.deleteManagePackBtn);
  }
};

window.MemeManagerUI.pack.createSyncStatusSection = function (title, categories, actionsBuilder = null) {
  const section = document.createElement("div");
  section.className = "status-section";
  const heading = document.createElement("h4");
  heading.textContent = title;
  section.append(heading);
  const list = document.createElement("ul");
  categories.forEach((category) => {
    const item = document.createElement("li");
    const label = document.createElement("span");
    label.textContent = category;
    item.append(label);
    if (actionsBuilder) item.append(actionsBuilder(category));
    list.append(item);
  });
  section.append(list);
  return section;
};

window.MemeManagerUI.pack.normalizeSyncDifferences = function (payload) {
  const source = payload?.differences && typeof payload.differences === "object"
    ? payload.differences
    : payload;
  return {
    missing_in_config: Array.isArray(source?.missing_in_config) ? source.missing_in_config : [],
    deleted_categories: Array.isArray(source?.deleted_categories) ? source.deleted_categories : [],
  };
};

window.MemeManagerUI.pack.renderSyncStatus = function (statusDiv, payload) {
  statusDiv.replaceChildren();
  const differences = window.MemeManagerUI.pack.normalizeSyncDifferences(payload);
  if (!differences.missing_in_config.length && !differences.deleted_categories.length) {
    const text = document.createElement("p");
    text.textContent = "配置与文件夹结构一致！";
    statusDiv.append(text);
    return;
  }
  if (differences.missing_in_config.length) {
    statusDiv.append(
      window.MemeManagerUI.pack.createSyncStatusSection(
        "新增类别（需要添加到配置）：",
        differences.missing_in_config,
        () => window.MemeManagerUI.emoji.createButton({
          className: "sync-btn",
          text: "同步配置",
          onClick: window.MemeManagerUI.pack.syncConfig,
        }),
      ),
    );
  }
  if (differences.deleted_categories.length) {
    statusDiv.append(
      window.MemeManagerUI.pack.createSyncStatusSection(
        "已删除的类别（配置中仍存在）：",
        differences.deleted_categories,
        (category) => window.MemeManagerUI.emoji.createButton({
          className: "remove-btn",
          text: "从配置中删除",
          onClick: () => window.MemeManagerUI.pack.removeFromConfig(category),
        }),
      ),
    );
  }
};

window.MemeManagerUI.pack.checkSyncStatus = async function (showToast = true) {
  const statusDiv = document.getElementById("sync-status");
  const button = document.getElementById("check-sync-btn");
  if (!statusDiv) return;
  window.MemeManagerUI.emoji.setButtonBusy(button, "正在检查中...");
  try {
    const data = await window.MemeManagerUI.api.apiGet("sync/status");
    if (data?.status === "error") throw new Error(data.message || "检查失败");
    window.MemeManagerUI.pack.renderSyncStatus(statusDiv, data);
    if (showToast) {
      window.MemeManagerUI.dialogs.showToast("配置状态已刷新。", "success", "检查完成");
    }
  } catch (error) {
    statusDiv.textContent = `检查同步状态失败：${error?.message || String(error)}`;
    if (showToast) {
      window.MemeManagerUI.dialogs.showToast(
        error?.message || String(error),
        "error",
        "检查失败",
      );
    }
  } finally {
    window.MemeManagerUI.emoji.restoreButton(button);
  }
};

window.MemeManagerUI.pack.syncConfig = async function () {
  try {
    await window.MemeManagerUI.api.apiPost("sync/config");
    await window.MemeManagerUI.emoji.refreshUi({ emojis: true, syncStatus: true });
    window.MemeManagerUI.dialogs.showToast("配置已同步到最新状态。", "success", "同步成功");
  } catch (error) {
    window.MemeManagerUI.dialogs.showToast(
      error?.message || String(error),
      "error",
      "同步失败",
    );
  }
};

window.MemeManagerUI.pack.removeFromConfig = async function (category) {
  const confirmed = await window.MemeManagerUI.dialogs.showConfirm({
    title: "从配置中删除类别",
    description: `确定要从配置中删除「${category}」吗？不会删除磁盘文件。`,
    confirmLabel: "确认删除",
    confirmClassName: "danger",
  });
  if (!confirmed) return;
  try {
    await window.MemeManagerUI.api.apiPost("category/remove_from_config", { category });
    await window.MemeManagerUI.emoji.refreshUi({ syncStatus: true });
    window.MemeManagerUI.dialogs.showToast(
      `类别「${category}」已从配置中移除。`,
      "success",
      "移除成功",
    );
  } catch (error) {
    window.MemeManagerUI.dialogs.showToast(
      error?.message || String(error),
      "error",
      "移除失败",
    );
  }
};
