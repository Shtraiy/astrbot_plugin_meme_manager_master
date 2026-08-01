window.MemeManagerUI = window.MemeManagerUI || {};
window.MemeManagerUI.pack = window.MemeManagerUI.pack || {};
window.MemeManagerUI.pack.formatPackOptionLabel = function (pack) {
    const name = String(pack?.name || pack?.id || "未命名");
    const id = String(pack?.id || "").trim();
    const imageCount = Number(pack?.image_count || 0);
    return `${name} (${id}) · ${imageCount} 张`;
  }
window.MemeManagerUI.pack.setPackTransferResult = function (element, message = "", type = "") {
    if (!element) {
      return;
    }
    element.textContent = String(message || "");
    element.classList.toggle("success", type === "success");
    element.classList.toggle("error", type === "error");
  }
window.MemeManagerUI.pack.selectedExportMode = function () {
    return (
      window.MemeManagerUI.state.exportModeInputs.find((input) => input.checked)?.value || "share"
    );
  }
window.MemeManagerUI.pack.updateExportModeAppearance = function () {
    window.MemeManagerUI.state.exportModeInputs.forEach((input) => {
      const option = input.closest(".export-mode-option");
      option?.classList.toggle("selected", input.checked);
      option?.classList.toggle("disabled", input.disabled);
    });
    if (window.MemeManagerUI.state.exportPackDownloadBtn) {
      window.MemeManagerUI.state.exportPackDownloadBtn.innerHTML =
        window.MemeManagerUI.pack.selectedExportMode() === "backup"
          ? '<i class="fas fa-download icon"></i>下载自用备份'
          : '<i class="fas fa-download icon"></i>下载分享版';
    }
  }
window.MemeManagerUI.pack.refreshPackExportCapability = async function (packId = window.MemeManagerUI.state.activeManagePackId) {
    const normalizedPackId = String(packId || "").trim();
    const requestId = ++window.MemeManagerUI.state.exportCapabilityRequestId;
    const pack = window.MemeManagerUI.state.managePacksById.get(normalizedPackId);
    if (window.MemeManagerUI.state.transferCurrentPack) {
      window.MemeManagerUI.state.transferCurrentPack.textContent = pack
        ? `当前：${pack.name || pack.id} · ${Number(pack.image_count || 0)} 张`
        : normalizedPackId
          ? `当前：${normalizedPackId}`
          : "暂无可导出的表情包";
    }
    if (!normalizedPackId) {
      if (window.MemeManagerUI.state.exportPackDownloadBtn) window.MemeManagerUI.state.exportPackDownloadBtn.disabled = true;
      if (window.MemeManagerUI.state.exportModeBackup) window.MemeManagerUI.state.exportModeBackup.disabled = true;
      if (window.MemeManagerUI.state.vectorBackupHint) window.MemeManagerUI.state.vectorBackupHint.textContent = "当前没有可导出的表情包。";
      window.MemeManagerUI.pack.updateExportModeAppearance();
      return;
    }

    if (window.MemeManagerUI.state.exportPackDownloadBtn) window.MemeManagerUI.state.exportPackDownloadBtn.disabled = false;
    if (window.MemeManagerUI.state.exportModeBackup) {
      if (window.MemeManagerUI.state.exportModeBackup.checked) {
        const shareInput = document.getElementById("export-mode-share");
        if (shareInput) shareInput.checked = true;
      }
      window.MemeManagerUI.state.exportModeBackup.disabled = true;
    }
    if (window.MemeManagerUI.state.vectorBackupHint) window.MemeManagerUI.state.vectorBackupHint.textContent = "正在检查当前表情包的向量状态…";
    window.MemeManagerUI.pack.updateExportModeAppearance();
    try {
      const status = await window.MemeManagerUI.api.apiGet("packs/export/status", {
        pack_id: normalizedPackId,
      });
      if (requestId !== window.MemeManagerUI.state.exportCapabilityRequestId) {
        return;
      }
      const available = Boolean(status?.vector_backup_available);
      if (window.MemeManagerUI.state.exportModeBackup) window.MemeManagerUI.state.exportModeBackup.disabled = !available;
      if (!available && window.MemeManagerUI.state.exportModeBackup?.checked) {
        const shareInput = document.getElementById("export-mode-share");
        if (shareInput) shareInput.checked = true;
      }
      if (window.MemeManagerUI.state.vectorBackupHint) {
        const modelHint = [
          String(status?.embedding_model || "").trim(),
          Number(status?.embedding_dimension || 0)
            ? `${Number(status.embedding_dimension)} 维`
            : "",
        ]
          .filter(Boolean)
          .join(" · ");
        window.MemeManagerUI.state.vectorBackupHint.textContent = available
          ? `包含完整本机向量${modelHint ? `（${modelHint}）` : ""}，适合迁回相同模型环境。`
          : "当前没有完整向量；完成语义化并建立索引后才可导出。";
      }
    } catch (error) {
      if (requestId !== window.MemeManagerUI.state.exportCapabilityRequestId) {
        return;
      }
      if (window.MemeManagerUI.state.exportModeBackup) window.MemeManagerUI.state.exportModeBackup.disabled = true;
      if (window.MemeManagerUI.state.vectorBackupHint) {
        window.MemeManagerUI.state.vectorBackupHint.textContent = "暂时无法读取向量状态，请稍后重试。";
      }
    } finally {
      if (requestId === window.MemeManagerUI.state.exportCapabilityRequestId) {
        window.MemeManagerUI.pack.updateExportModeAppearance();
      }
    }
  }
window.MemeManagerUI.pack.downloadCurrentPack = async function () {
    const packId = String(window.MemeManagerUI.state.activeManagePackId || "").trim();
    if (!packId) {
      window.MemeManagerUI.dialogs.showToast("当前没有可导出的表情包。", "warning", "无法导出");
      return;
    }
    const mode = window.MemeManagerUI.pack.selectedExportMode();
    window.MemeManagerUI.emoji.setButtonBusy(window.MemeManagerUI.state.exportPackDownloadBtn, "正在生成压缩包…");
    window.MemeManagerUI.pack.setPackTransferResult(window.MemeManagerUI.state.exportPackResult, "正在整理文件，请不要关闭页面。", "");
    try {
      await window.AstrBotPluginPage.download("packs/export/download", {
        pack_id: packId,
        mode,
      });
      const label = mode === "backup" ? "带向量自用备份" : "无向量分享版";
      window.MemeManagerUI.pack.setPackTransferResult(
        window.MemeManagerUI.state.exportPackResult,
        `${label}已生成，并已开始下载。`,
        "success",
      );
      window.MemeManagerUI.dialogs.showToast(`${label}已开始下载。`, "success", "导出成功");
    } catch (error) {
      window.MemeManagerUI.pack.setPackTransferResult(
        window.MemeManagerUI.state.exportPackResult,
        error?.message || String(error),
        "error",
      );
      window.MemeManagerUI.dialogs.showToast(error?.message || String(error), "error", "导出失败");
    } finally {
      window.MemeManagerUI.emoji.restoreButton(window.MemeManagerUI.state.exportPackDownloadBtn);
      window.MemeManagerUI.pack.updateExportModeAppearance();
    }
  }
window.MemeManagerUI.pack.resetPackImportPreview = function ({ keepResult = false } = {}) {
    window.MemeManagerUI.state.pendingPackImportToken = "";
    if (window.MemeManagerUI.state.packImportFile) window.MemeManagerUI.state.packImportFile.value = "";
    if (window.MemeManagerUI.state.packImportFileLabel) window.MemeManagerUI.state.packImportFileLabel.textContent = "选择或拖入 zip 压缩包";
    window.MemeManagerUI.state.packImportDropzone?.classList.remove("hidden");
    window.MemeManagerUI.state.packImportPreview?.classList.add("hidden");
    window.MemeManagerUI.state.packImportWarning?.classList.add("hidden");
    if (window.MemeManagerUI.state.packImportSetDefault) window.MemeManagerUI.state.packImportSetDefault.checked = false;
    if (window.MemeManagerUI.state.packImportOverwrite) window.MemeManagerUI.state.packImportOverwrite.checked = false;
    if (window.MemeManagerUI.state.packImportOverwriteManual) window.MemeManagerUI.state.packImportOverwriteManual.checked = false;
    if (!keepResult) window.MemeManagerUI.pack.setPackTransferResult(window.MemeManagerUI.state.packImportResult, "", "");
  }
window.MemeManagerUI.pack.renderPackImportInspection = function (data) {
    const formatLabels = {
      v2: data?.export_mode === "backup" ? "新版带向量备份" : "新版分享包",
      v1: "兼容版资源包",
      legacy: "旧版无语义包 · 将自动转换",
    };
    if (window.MemeManagerUI.state.packImportPreviewName) {
      window.MemeManagerUI.state.packImportPreviewName.textContent = `${data?.name || data?.pack_id || "待导入表情包"} (${data?.pack_id || "未知 ID"})`;
    }
    if (window.MemeManagerUI.state.packImportPreviewFormat) {
      window.MemeManagerUI.state.packImportPreviewFormat.textContent =
        formatLabels[data?.detected_format] || "已识别的表情包";
    }
    if (window.MemeManagerUI.state.packImportImageCount) {
      window.MemeManagerUI.state.packImportImageCount.textContent = Number(data?.image_count || 0);
    }
    if (window.MemeManagerUI.state.packImportCategoryCount) {
      window.MemeManagerUI.state.packImportCategoryCount.textContent = Number(data?.category_count || 0);
    }
    if (window.MemeManagerUI.state.packImportSemanticCount) {
      window.MemeManagerUI.state.packImportSemanticCount.textContent = data?.semantic_metadata
        ? `${Number(data?.semantic_done || 0)} 条`
        : "无";
    }
    if (window.MemeManagerUI.state.packImportVectorState) {
      window.MemeManagerUI.state.packImportVectorState.textContent = data?.vectors_present
        ? "包含，将校验"
        : "不包含";
    }
    const warnings = Array.isArray(data?.warnings) ? data.warnings : [];
    if (window.MemeManagerUI.state.packImportWarning) {
      window.MemeManagerUI.state.packImportWarning.textContent = warnings.join(" ");
      window.MemeManagerUI.state.packImportWarning.classList.toggle("hidden", warnings.length === 0);
    }
    window.MemeManagerUI.state.packImportDropzone?.classList.add("hidden");
    window.MemeManagerUI.state.packImportPreview?.classList.remove("hidden");
  }
window.MemeManagerUI.pack.stagePackImport = async function (file) {
    if (!file) {
      return;
    }
    if (!String(file.name || "").toLowerCase().endsWith(".zip")) {
      window.MemeManagerUI.dialogs.showToast("请选择 zip 格式的表情包。", "warning", "格式不支持");
      return;
    }
    window.MemeManagerUI.state.pendingPackImportToken = "";
    if (window.MemeManagerUI.state.packImportFileLabel) window.MemeManagerUI.state.packImportFileLabel.textContent = `正在检查 ${file.name}…`;
    window.MemeManagerUI.state.packImportDropzone?.classList.add("checking");
    window.MemeManagerUI.pack.setPackTransferResult(window.MemeManagerUI.state.packImportResult, "正在检查压缩包结构和兼容性…", "");
    try {
      const data = await window.AstrBotPluginPage.upload(
        "packs/import/stage",
        file,
      );
      window.MemeManagerUI.state.pendingPackImportToken = String(data?.import_token || "").trim();
      if (!window.MemeManagerUI.state.pendingPackImportToken) {
        throw new Error("服务器没有返回导入凭证");
      }
      window.MemeManagerUI.pack.renderPackImportInspection(data);
      window.MemeManagerUI.pack.setPackTransferResult(window.MemeManagerUI.state.packImportResult, "检查完成，请确认导入选项。", "success");
    } catch (error) {
      window.MemeManagerUI.pack.resetPackImportPreview({ keepResult: true });
      window.MemeManagerUI.pack.setPackTransferResult(
        window.MemeManagerUI.state.packImportResult,
        error?.message || String(error),
        "error",
      );
      window.MemeManagerUI.dialogs.showToast(error?.message || String(error), "error", "压缩包检查失败");
    } finally {
      window.MemeManagerUI.state.packImportDropzone?.classList.remove("checking");
    }
  }
window.MemeManagerUI.pack.confirmPackImport = async function () {
    if (!window.MemeManagerUI.state.pendingPackImportToken) {
      window.MemeManagerUI.dialogs.showToast("请先选择并检查压缩包。", "warning", "无法导入");
      return;
    }
    if (window.MemeManagerUI.state.packImportOverwrite?.checked) {
      const confirmed = await window.MemeManagerUI.dialogs.showConfirm({
        title: "确认覆盖同名表情包？",
        description: window.MemeManagerUI.state.packImportOverwriteManual?.checked
          ? "原表情包、向量和本机人工语义都会被替换。建议先导出自用备份。"
          : "原表情包及其向量会被替换，但本机人工描述、标签和图片文字会保留。",
        confirmLabel: "确认覆盖并导入",
        confirmClassName: "danger",
      });
      if (!confirmed) {
        return;
      }
    }

    window.MemeManagerUI.emoji.setButtonBusy(window.MemeManagerUI.state.packImportConfirmBtn, "正在导入…");
    window.MemeManagerUI.pack.setPackTransferResult(window.MemeManagerUI.state.packImportResult, "正在安装表情包，请不要关闭页面。", "");
    try {
      const data = await window.MemeManagerUI.api.apiPost("packs/import/apply", {
        import_token: window.MemeManagerUI.state.pendingPackImportToken,
        overwrite: Boolean(window.MemeManagerUI.state.packImportOverwrite?.checked),
        overwrite_manual_semantics: Boolean(
          window.MemeManagerUI.state.packImportOverwrite?.checked && window.MemeManagerUI.state.packImportOverwriteManual?.checked,
        ),
        set_as_default: Boolean(window.MemeManagerUI.state.packImportSetDefault?.checked),
      });
      const importedPackId = String(data?.pack_id || "").trim();
      const vectorHint = data?.vectors_restored
        ? "，向量已恢复"
        : data?.vector_warning
          ? `；${data.vector_warning}`
          : "";
      window.MemeManagerUI.pack.resetPackImportPreview({ keepResult: true });
      window.MemeManagerUI.pack.setPackTransferResult(
        window.MemeManagerUI.state.packImportResult,
        `已导入 ${data?.name || importedPackId}${vectorHint}`,
        "success",
      );
      await window.MemeManagerUI.pack.loadManagePackSwitcher(importedPackId);
      await window.MemeManagerUI.emoji.refreshUi({ emojis: true, syncStatus: true });
      await window.MemeManagerUI.pack.refreshPackExportCapability(importedPackId);
      window.MemeManagerUI.dialogs.showToast(`表情包 ${importedPackId} 已导入。`, "success", "导入成功");
    } catch (error) {
      window.MemeManagerUI.pack.setPackTransferResult(
        window.MemeManagerUI.state.packImportResult,
        error?.message || String(error),
        "error",
      );
      window.MemeManagerUI.dialogs.showToast(error?.message || String(error), "error", "导入失败");
    } finally {
      window.MemeManagerUI.emoji.restoreButton(window.MemeManagerUI.state.packImportConfirmBtn);
    }
  }
window.MemeManagerUI.pack.refreshManagePackSummaries = async function () {
    try {
      const response = await window.MemeManagerUI.api.apiGet("packs");
      const packs = Array.isArray(response?.packs) ? response.packs : [];
      window.MemeManagerUI.state.managePacksById = new Map(
        packs.map((pack) => [String(pack?.id || "").trim(), pack]),
      );
      Array.from(window.MemeManagerUI.state.managePackSelect?.options || []).forEach((option) => {
        const pack = window.MemeManagerUI.state.managePacksById.get(String(option.value || "").trim());
        if (pack) {
          option.textContent = window.MemeManagerUI.pack.formatPackOptionLabel(pack);
        }
      });
      await window.MemeManagerUI.pack.refreshPackExportCapability(
        window.MemeManagerUI.state.activeManagePackId,
      );
      return packs;
    } catch (error) {
      console.warn("刷新图包语义状态失败:", error);
      return [];
    }
  }
window.MemeManagerUI.pack.syncManagedPackQuery = function (managedPackId) {
    const nextUrl = new URL(window.location.href);
    const normalized = String(managedPackId || "").trim();
    if (normalized) {
      nextUrl.searchParams.set("managed_pack_id", normalized);
    } else {
      nextUrl.searchParams.delete("managed_pack_id");
    }
    window.history.replaceState(null, "", nextUrl.toString());
  }
window.MemeManagerUI.pack.buildCatalogPageUrl = function () {
    return window.MemeManagerUI.api.withCurrentPageParams("../catalog/index.html", {
      view: "catalog",
    }).toString();
  }
window.MemeManagerUI.pack.openCatalogPage = function () {
    window.location.href = window.MemeManagerUI.pack.buildCatalogPageUrl();
  }
window.MemeManagerUI.pack.isSingleEmptyPack = function (packs) {
    if (!Array.isArray(packs) || packs.length !== 1) {
      return false;
    }
    const onlyPack = packs[0] || {};
    return Number(onlyPack?.image_count || 0) === 0;
  }
window.MemeManagerUI.pack.maybeShowFirstUseCatalogGuide = async function (packs) {
    if (window.MemeManagerUI.state.firstUseCatalogGuideShown || !window.MemeManagerUI.pack.isSingleEmptyPack(packs)) {
      return;
    }

    window.MemeManagerUI.state.firstUseCatalogGuideShown = true;
    const confirmed = await window.MemeManagerUI.dialogs.showConfirm({
      title: "第一次使用？",
      description: "可以前往资源广场下载官方表情包哦。",
      confirmLabel: "前往广场",
    });
    if (!confirmed) {
      return;
    }
    await window.MemeManagerUI.pack.openCatalogPage();
  }
window.MemeManagerUI.pack.loadManagePackSwitcher = async function (preferredPackId = "") {
    if (!window.MemeManagerUI.state.managePackSelect) {
      return [];
    }
    try {
      const response = await window.MemeManagerUI.api.apiGet("packs");
      const packs = Array.isArray(response?.packs) ? response.packs : [];
      window.MemeManagerUI.state.managePacksById = new Map(
        packs.map((pack) => [String(pack?.id || "").trim(), pack]),
      );
      window.MemeManagerUI.state.managePackSelect.innerHTML = "";

      if (!packs.length) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "暂无可用表情包";
        window.MemeManagerUI.state.managePackSelect.appendChild(option);
        window.MemeManagerUI.state.managePackSelect.disabled = true;
        window.MemeManagerUI.state.activeManagePackId = "";
        await window.MemeManagerUI.pack.refreshPackExportCapability("");
        if (window.MemeManagerUI.state.switchManagePackBtn) {
          window.MemeManagerUI.state.switchManagePackBtn.disabled = true;
        }
        if (window.MemeManagerUI.state.deleteManagePackBtn) {
          window.MemeManagerUI.state.deleteManagePackBtn.disabled = true;
        }
        return packs;
      }

      let selectedPackId = "";
      window.MemeManagerUI.state.defaultManagePackId = "";
      packs.forEach((pack) => {
        const option = document.createElement("option");
        option.value = String(pack.id || "").trim();
        option.textContent = window.MemeManagerUI.pack.formatPackOptionLabel(pack);
        if (!selectedPackId) {
          selectedPackId = option.value;
        }
        if (!window.MemeManagerUI.state.defaultManagePackId && pack?.is_default) {
          window.MemeManagerUI.state.defaultManagePackId = option.value;
        }
        window.MemeManagerUI.state.managePackSelect.appendChild(option);
      });

      if (!window.MemeManagerUI.state.defaultManagePackId) {
        window.MemeManagerUI.state.defaultManagePackId = selectedPackId;
      }

      window.MemeManagerUI.state.managePackSelect.disabled = false;
      if (window.MemeManagerUI.state.switchManagePackBtn) {
        window.MemeManagerUI.state.switchManagePackBtn.disabled = false;
      }
      if (window.MemeManagerUI.state.deleteManagePackBtn) {
        window.MemeManagerUI.state.deleteManagePackBtn.disabled = false;
      }
      const preferred = String(preferredPackId || "").trim();
      const canUsePreferred = packs.some(
        (item) => String(item?.id || "").trim() === preferred,
      );
      const canUseUrlPack = packs.some(
        (item) => String(item?.id || "").trim() === window.MemeManagerUI.state.managedPackIdFromUrl,
      );
      if (canUsePreferred) {
        selectedPackId = preferred;
      } else if (canUseUrlPack) {
        selectedPackId = window.MemeManagerUI.state.managedPackIdFromUrl;
      }
      window.MemeManagerUI.state.managePackSelect.value = selectedPackId;
      window.MemeManagerUI.state.activeManagePackId = selectedPackId;
      window.MemeManagerUI.pack.syncManagedPackQuery(selectedPackId);
      await window.MemeManagerUI.pack.refreshPackExportCapability(selectedPackId);

      await window.MemeManagerUI.pack.maybeShowFirstUseCatalogGuide(packs);
      return packs;
    } catch (error) {
      window.MemeManagerUI.dialogs.showToast(error?.message || String(error), "error", "加载表情包失败");
      return [];
    }
  }
window.MemeManagerUI.pack.switchManagePack = async function () {
    if (!window.MemeManagerUI.state.managePackSelect) {
      return;
    }
    const targetPackId = String(window.MemeManagerUI.state.managePackSelect.value || "").trim();
    if (!targetPackId) {
      window.MemeManagerUI.dialogs.showToast("请先选择表情包。", "warning", "切换失败");
      return;
    }

    window.MemeManagerUI.emoji.setButtonBusy(window.MemeManagerUI.state.switchManagePackBtn, "切换中...");
    window.MemeManagerUI.emoji.closeImagePreview();
    const previousActivePackId = window.MemeManagerUI.state.activeManagePackId;
    window.MemeManagerUI.state.activeManagePackId = targetPackId;
    try {
      window.MemeManagerUI.pack.syncManagedPackQuery(targetPackId);
      await window.MemeManagerUI.emoji.refreshUi({ emojis: true });
      await window.MemeManagerUI.pack.refreshPackExportCapability(targetPackId);
      window.MemeManagerUI.dialogs.showToast(`已切换管理视图到 ${targetPackId}。`, "success", "切换成功");
    } catch (error) {
      window.MemeManagerUI.state.activeManagePackId = previousActivePackId;
      window.MemeManagerUI.pack.syncManagedPackQuery(previousActivePackId);
      await window.MemeManagerUI.pack.refreshPackExportCapability(previousActivePackId);
      window.MemeManagerUI.dialogs.showToast(error?.message || String(error), "error", "切换失败");
    } finally {
      window.MemeManagerUI.emoji.restoreButton(window.MemeManagerUI.state.switchManagePackBtn);
    }
  }
window.MemeManagerUI.pack.deleteCurrentManagePack = async function () {
    if (!window.MemeManagerUI.state.managePackSelect) {
      return;
    }

    const targetPackId = String(
      window.MemeManagerUI.state.activeManagePackId || window.MemeManagerUI.state.managePackSelect.value || "",
    ).trim();
    if (!targetPackId) {
      window.MemeManagerUI.dialogs.showToast("请先选择要删除的表情包。", "warning", "删除失败");
      return;
    }

    const confirmed = await window.MemeManagerUI.dialogs.showDangerConfirm({
      title: `删除表情包组「${targetPackId}」`,
      description:
        "该操作会删除整个表情包组（包括分类与图片）。删除后会自动切换到其他表情包；如果删空会自动创建一个空表情包。",
      actionLabel: "确认删除当前表情包组",
      countdown: 5,
    });
    if (!confirmed) {
      return;
    }

    window.MemeManagerUI.emoji.setButtonBusy(window.MemeManagerUI.state.deleteManagePackBtn, "删除中...");
    try {
      const data = await window.MemeManagerUI.api.apiPost("packs/uninstall", { pack_id: targetPackId });
      const switchedPackId = String(data?.switched_default_to || "").trim();
      await window.MemeManagerUI.pack.loadManagePackSwitcher(switchedPackId);
      await window.MemeManagerUI.emoji.refreshUi({ emojis: true, syncStatus: true });
      const switchedHint = switchedPackId ? `，已切换到 ${switchedPackId}` : "";
      const createdHint = data?.auto_created_empty_pack
        ? "（已自动创建空表情包）"
        : "";
      window.MemeManagerUI.dialogs.showToast(
        `已删除 ${targetPackId}${switchedHint}${createdHint}`,
        "success",
        "删除成功",
      );
    } catch (error) {
      window.MemeManagerUI.dialogs.showToast(error?.message || String(error), "error", "删除失败", 4500);
    } finally {
      window.MemeManagerUI.emoji.restoreButton(window.MemeManagerUI.state.deleteManagePackBtn);
    }
  }
window.MemeManagerUI.pack.installOfficialFirstPackFromHint = async function (triggerBtn) {
    window.MemeManagerUI.emoji.setButtonBusy(triggerBtn, "安装中...");
    try {
      const data = await window.MemeManagerUI.api.apiPost("community/install_official_first", {
        overwrite: false,
        set_as_default: true,
      });
      const installedPackId = String(data?.pack_id || "").trim();
      await window.MemeManagerUI.pack.loadManagePackSwitcher(installedPackId);
      await window.MemeManagerUI.emoji.refreshUi({ emojis: true, syncStatus: true });
      const installedName = String(
        data?.selected_pack_name ||
          data?.name ||
          installedPackId ||
          "官方表情包",
      );
      window.MemeManagerUI.dialogs.showToast(
        `已安装 ${installedName}，并切换为默认表情包。`,
        "success",
        "安装成功",
      );
    } catch (error) {
      window.MemeManagerUI.dialogs.showToast(error?.message || String(error), "error", "安装失败");
    } finally {
      window.MemeManagerUI.emoji.restoreButton(triggerBtn);
    }
  }
window.MemeManagerUI.pack.createSyncStatusSection = function (title, categories, actionsBuilder = null) {
    const section = document.createElement("div");
    section.className = "status-section";

    const heading = document.createElement("h4");
    heading.textContent = title;
    section.appendChild(heading);

    const list = document.createElement("ul");
    categories.forEach((category) => {
      const item = document.createElement("li");
      const label = document.createElement("span");
      label.textContent = category;
      item.appendChild(label);

      if (actionsBuilder) {
        item.appendChild(actionsBuilder(category));
      }

      list.appendChild(item);
    });
    section.appendChild(list);

    return section;
  }
window.MemeManagerUI.pack.normalizeSyncDifferences = function (payload) {
    const source =
      payload &&
      typeof payload.differences === "object" &&
      payload.differences !== null
        ? payload.differences
        : payload;

    return {
      missing_in_config: Array.isArray(source?.missing_in_config)
        ? source.missing_in_config
        : [],
      deleted_categories: Array.isArray(source?.deleted_categories)
        ? source.deleted_categories
        : [],
    };
  }
window.MemeManagerUI.pack.renderSyncStatus = function (statusDiv, differences) {
    statusDiv.innerHTML = "";
    const fragments = [];
    const normalizedDifferences = window.MemeManagerUI.pack.normalizeSyncDifferences(differences);

    if (normalizedDifferences.missing_in_config.length > 0) {
      fragments.push(
        window.MemeManagerUI.pack.createSyncStatusSection(
          "新增类别（需要添加到配置）：",
          normalizedDifferences.missing_in_config,
          () =>
            window.MemeManagerUI.emoji.createButton({
              className: "sync-btn",
              text: "同步配置",
              onClick: () => window.MemeManagerUI.pack.syncConfig(),
            }),
        ),
      );
    }

    if (normalizedDifferences.deleted_categories.length > 0) {
      fragments.push(
        window.MemeManagerUI.pack.createSyncStatusSection(
          "已删除的类别（配置中仍存在）：",
          normalizedDifferences.deleted_categories,
          (category) => {
            const actions = document.createElement("div");
            actions.className = "action-buttons";
            actions.appendChild(
              window.MemeManagerUI.emoji.createButton({
                className: "restore-btn",
                text: "恢复类别",
                onClick: () => window.MemeManagerUI.pack.restoreCategory(category),
              }),
            );
            actions.appendChild(
              window.MemeManagerUI.emoji.createButton({
                className: "remove-btn",
                text: "从配置中删除",
                onClick: () => window.MemeManagerUI.pack.removeFromConfig(category),
              }),
            );
            return actions;
          },
        ),
      );
    }

    if (fragments.length === 0) {
      const text = document.createElement("p");
      text.textContent = "配置与文件夹结构一致！";
      statusDiv.appendChild(text);
      return;
    }

    fragments.forEach((fragment) => {
      statusDiv.appendChild(fragment);
    });

    const syncActions = document.createElement("div");
    syncActions.className = "sync-actions";
    syncActions.appendChild(
      window.MemeManagerUI.emoji.createButton({
        className: "main-sync-btn",
        text: "同步所有配置",
        onClick: () => window.MemeManagerUI.pack.syncConfig(),
      }),
    );
    statusDiv.appendChild(syncActions);
  }
window.MemeManagerUI.pack.renderSyncStatusError = function (statusDiv, message) {
    statusDiv.innerHTML = "";

    const errorText = document.createElement("p");
    errorText.style.color = "red";
    errorText.textContent = `检查同步状态失败: ${message}`;
    statusDiv.appendChild(errorText);

    statusDiv.appendChild(
      window.MemeManagerUI.emoji.createButton({
        className: "retry-btn",
        text: "重试",
        onClick: () => window.MemeManagerUI.pack.checkSyncStatus(),
      }),
    );
  }
window.MemeManagerUI.pack.checkSyncStatus = async function (showAlert = true) {
    const statusDiv = document.getElementById("sync-status");
    if (!statusDiv) return;

    const btn = document.getElementById("check-sync-btn");
    window.MemeManagerUI.emoji.setButtonBusy(btn, "正在检查中...");

    try {
      const data = await window.MemeManagerUI.api.apiGet("sync/status");
      if (data.status === "error") throw new Error(data.message);

      const differences = window.MemeManagerUI.pack.normalizeSyncDifferences(data);
      window.MemeManagerUI.pack.renderSyncStatus(statusDiv, differences);

      if (showAlert) {
        window.MemeManagerUI.dialogs.showToast("配置状态已刷新。", "success", "检查完成");
      }
    } catch (error) {
      console.error("检查同步状态失败:", error);
      window.MemeManagerUI.pack.renderSyncStatusError(statusDiv, error.message);
      if (showAlert) {
        window.MemeManagerUI.dialogs.showToast(error.message, "error", "检查失败");
      }
    } finally {
      window.MemeManagerUI.emoji.restoreButton(btn);
    }
  }
window.MemeManagerUI.pack.syncConfig = async function () {
    try {
      await window.MemeManagerUI.api.apiPost("sync/config");
      await window.MemeManagerUI.emoji.refreshUi({ emojis: true, syncStatus: true });
      window.MemeManagerUI.dialogs.showToast("配置已同步到最新状态。", "success", "同步成功");
    } catch (error) {
      console.error("同步配置失败:", error);
      window.MemeManagerUI.dialogs.showToast(error.message, "error", "同步失败");
    }
  }
window.MemeManagerUI.pack.restoreCategory = async function (category) {
    try {
      const data = await window.MemeManagerUI.api.apiPost("category/restore", { category });

      await window.MemeManagerUI.emoji.refreshUi({ emojis: true, syncStatus: true });
      window.MemeManagerUI.dialogs.showToast(
        `类别「${category}」已恢复。\n描述：${data.description || "请补充描述"}`,
        "success",
        "恢复成功",
      );
    } catch (error) {
      console.error("恢复类别失败:", error);
      window.MemeManagerUI.dialogs.showToast(error.message, "error", "恢复失败");
    }
  }
window.MemeManagerUI.pack.removeFromConfig = async function (category) {
    const confirmed = await window.MemeManagerUI.dialogs.showConfirm({
      title: "从配置中删除类别",
      description: `确定要从配置中删除「${category}」吗？该操作不会删除磁盘上的文件夹，只会移除配置记录。`,
      confirmLabel: "确认删除",
      confirmClassName: "danger",
    });
    if (!confirmed) {
      return;
    }

    try {
      await window.MemeManagerUI.api.apiPost("category/remove_from_config", { category });

      await window.MemeManagerUI.emoji.refreshUi({ syncStatus: true });
      window.MemeManagerUI.dialogs.showToast(`类别「${category}」已从配置中移除。`, "success", "移除成功");
    } catch (error) {
      console.error("从配置中删除类别失败:", error);
      window.MemeManagerUI.dialogs.showToast(error.message, "error", "移除失败");
    }
  }
