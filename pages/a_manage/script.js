async function initApp() {
  await window.AstrBotPluginPage.ready();
  window.AstrBotPluginPage.getContext();
  await window.MemeManagerUI.api.applySecureNavLinks();
  if (window.MemeManagerUI.state.toggleSelectionModeBtn) {
    window.MemeManagerUI.state.toggleSelectionModeBtn.addEventListener("click", () => {
      window.MemeManagerUI.emoji.setSelectionMode(!window.MemeManagerUI.state.selectionState.enabled);
    });
  }

  if (window.MemeManagerUI.state.batchDeleteBtn) {
    window.MemeManagerUI.state.batchDeleteBtn.addEventListener("click", window.MemeManagerUI.emoji.batchDeleteSelected);
  }

  if (window.MemeManagerUI.state.batchMoveBtn) {
    window.MemeManagerUI.state.batchMoveBtn.addEventListener("click", () => {
      window.MemeManagerUI.emoji.openMoveTargetModal(Array.from(window.MemeManagerUI.state.selectionState.items.values()));
    });
  }

  if (window.MemeManagerUI.state.clearAllBtn) {
    window.MemeManagerUI.state.clearAllBtn.addEventListener("click", window.MemeManagerUI.emoji.clearAllEmojiFiles);
  }

  if (window.MemeManagerUI.state.contextMenuDeleteBtn) {
    window.MemeManagerUI.state.contextMenuDeleteBtn.addEventListener("click", async () => {
      const menuItems = window.MemeManagerUI.emoji.dedupeEmojiItems(window.MemeManagerUI.state.contextMenuState.items);
      window.MemeManagerUI.emoji.closeBatchContextMenu();
      await window.MemeManagerUI.emoji.deleteEmojiItems(menuItems, {
        useSelectionState:
          menuItems.length > 0 &&
          menuItems.every((item) => window.MemeManagerUI.emoji.isEmojiSelected(item.category, item.emoji)),
        confirmMode: "danger",
      });
    });
  }

  if (window.MemeManagerUI.state.contextMenuMoveBtn) {
    window.MemeManagerUI.state.contextMenuMoveBtn.addEventListener("click", async () => {
      const menuItems = window.MemeManagerUI.emoji.dedupeEmojiItems(window.MemeManagerUI.state.contextMenuState.items);
      window.MemeManagerUI.emoji.closeBatchContextMenu();
      const confirmed = await window.MemeManagerUI.dialogs.showConfirm({
        title: "移动表情包",
        description: `确认继续为这 ${menuItems.length} 个表情包选择目标分类？`,
        confirmLabel: "继续选择目标分类",
      });
      if (!confirmed) {
        return;
      }
      window.MemeManagerUI.emoji.openMoveTargetModal(menuItems);
    });
  }

  if (window.MemeManagerUI.state.contextMenuCopyBtn) {
    window.MemeManagerUI.state.contextMenuCopyBtn.addEventListener("click", async () => {
      const menuItems = window.MemeManagerUI.emoji.dedupeEmojiItems(window.MemeManagerUI.state.contextMenuState.items);
      window.MemeManagerUI.emoji.closeBatchContextMenu();
      const confirmed = await window.MemeManagerUI.dialogs.showConfirm({
        title: "复制表情包",
        description: `确认复制这 ${menuItems.length} 个表情包到 WebUI 剪贴板？`,
        confirmLabel: "确认复制",
      });
      if (!confirmed) {
        return;
      }
      window.MemeManagerUI.emoji.copyItemsToClipboard(menuItems);
    });
  }

  if (window.MemeManagerUI.state.contextMenuPasteBtn) {
    window.MemeManagerUI.state.contextMenuPasteBtn.addEventListener("click", async () => {
      const targetCategory = window.MemeManagerUI.state.contextMenuState.targetCategory;
      const clipboardItems = window.MemeManagerUI.emoji.getClipboardItems();
      window.MemeManagerUI.emoji.closeBatchContextMenu();
      const confirmed = await window.MemeManagerUI.dialogs.showConfirm({
        title: "粘贴表情包",
        description: `确认将剪贴板中的 ${clipboardItems.length} 个表情包粘贴到「${targetCategory}」？`,
        confirmLabel: "确认粘贴",
      });
      if (!confirmed) {
        return;
      }
      await window.MemeManagerUI.emoji.copyEmojiItemsToCategory(targetCategory, clipboardItems);
    });
  }

  if (window.MemeManagerUI.state.consoleToggleBtn) {
    window.MemeManagerUI.state.consoleToggleBtn.addEventListener("click", () => {
      window.MemeManagerUI.emoji.toggleConsolePanel();
    });
  }

  if (window.MemeManagerUI.state.directoryToggleBtn) {
    window.MemeManagerUI.state.directoryToggleBtn.addEventListener("click", () => {
      window.MemeManagerUI.emoji.toggleDirectoryPanel();
    });
  }

  if (window.MemeManagerUI.state.sidebarBackdrop) {
    window.MemeManagerUI.state.sidebarBackdrop.addEventListener("click", () => {
      window.MemeManagerUI.emoji.closeAllPanels();
      window.MemeManagerUI.emoji.updatePanelToggleState();
    });
  }

  if (window.MemeManagerUI.state.dangerModalAcknowledge) {
    window.MemeManagerUI.state.dangerModalAcknowledge.addEventListener("change", () => {
      if (window.MemeManagerUI.state.dangerConfirmStage === "ack") {
        if (!window.MemeManagerUI.state.dangerModalAcknowledge.checked) {
          window.MemeManagerUI.state.dangerModalConfirmBtn.disabled = true;
          window.MemeManagerUI.state.dangerModalConfirmBtn.textContent = "请先勾选上方选项";
          return;
        }
        window.MemeManagerUI.dialogs.startDangerCountdown();
      }
    });
  }

  if (window.MemeManagerUI.state.dangerModalCancelBtn) {
    window.MemeManagerUI.state.dangerModalCancelBtn.addEventListener("click", () => {
      window.MemeManagerUI.dialogs.closeDangerConfirm(false);
    });
  }

  if (window.MemeManagerUI.state.dangerModalConfirmBtn) {
    window.MemeManagerUI.state.dangerModalConfirmBtn.addEventListener("click", () => {
      if (window.MemeManagerUI.state.dangerConfirmStage === "ack" && window.MemeManagerUI.state.dangerModalAcknowledge?.checked) {
        window.MemeManagerUI.dialogs.startDangerCountdown();
        return;
      }
      if (window.MemeManagerUI.state.dangerConfirmStage === "ready") {
        window.MemeManagerUI.dialogs.closeDangerConfirm(true);
      }
    });
  }

  if (window.MemeManagerUI.state.dangerModalRoot) {
    window.MemeManagerUI.state.dangerModalRoot.addEventListener("click", (event) => {
      if (event.target === window.MemeManagerUI.state.dangerModalRoot) {
        window.MemeManagerUI.dialogs.closeDangerConfirm(false);
      }
    });
  }

  if (window.MemeManagerUI.state.confirmModalCancelBtn) {
    window.MemeManagerUI.state.confirmModalCancelBtn.addEventListener("click", () => {
      window.MemeManagerUI.dialogs.closeConfirm(false);
    });
  }

  if (window.MemeManagerUI.state.confirmModalConfirmBtn) {
    window.MemeManagerUI.state.confirmModalConfirmBtn.addEventListener("click", () => {
      window.MemeManagerUI.dialogs.closeConfirm(true);
    });
  }

  if (window.MemeManagerUI.state.confirmModalRoot) {
    window.MemeManagerUI.state.confirmModalRoot.addEventListener("click", (event) => {
      if (event.target === window.MemeManagerUI.state.confirmModalRoot) {
        window.MemeManagerUI.dialogs.closeConfirm(false);
      }
    });
  }

  if (window.MemeManagerUI.state.categoryEditCancelBtn) {
    window.MemeManagerUI.state.categoryEditCancelBtn.addEventListener("click", () => {
      window.MemeManagerUI.emoji.closeCategoryEditModal();
    });
  }

  if (window.MemeManagerUI.state.categoryEditSaveBtn) {
    window.MemeManagerUI.state.categoryEditSaveBtn.addEventListener("click", async () => {
      await window.MemeManagerUI.emoji.saveCategory();
    });
  }

  if (window.MemeManagerUI.state.moveTargetCancelBtn) {
    window.MemeManagerUI.state.moveTargetCancelBtn.addEventListener("click", () => {
      window.MemeManagerUI.emoji.closeMoveTargetModal();
    });
  }

  if (window.MemeManagerUI.state.moveTargetModalRoot) {
    window.MemeManagerUI.state.moveTargetModalRoot.addEventListener("click", (event) => {
      if (event.target === window.MemeManagerUI.state.moveTargetModalRoot) {
        window.MemeManagerUI.emoji.closeMoveTargetModal();
      }
    });
  }

  if (window.MemeManagerUI.state.imagePreviewCloseBtn) {
    window.MemeManagerUI.state.imagePreviewCloseBtn.addEventListener("click", () => {
      window.MemeManagerUI.emoji.closeImagePreview();
    });
  }

  if (window.MemeManagerUI.state.imagePreviewOriginalBtn) {
    window.MemeManagerUI.state.imagePreviewOriginalBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      void window.MemeManagerUI.emoji.showOriginalPreview();
    });
  }

  if (window.MemeManagerUI.state.imagePreviewModalRoot) {
    window.MemeManagerUI.state.imagePreviewModalRoot.addEventListener("click", (event) => {
      if (
        event.target === window.MemeManagerUI.state.imagePreviewModalRoot ||
        event.target?.classList?.contains("image-preview-stage")
      ) {
        window.MemeManagerUI.emoji.closeImagePreview();
      }
    });
  }

  if (window.MemeManagerUI.state.categoryEditModalRoot) {
    window.MemeManagerUI.state.categoryEditModalRoot.addEventListener("click", (event) => {
      if (event.target === window.MemeManagerUI.state.categoryEditModalRoot) {
        window.MemeManagerUI.emoji.closeCategoryEditModal();
      }
    });
  }

  [window.MemeManagerUI.state.categoryEditNameInput, window.MemeManagerUI.state.categoryEditDescInput].forEach((input) => {
    input?.addEventListener("keydown", async (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        await window.MemeManagerUI.emoji.saveCategory();
      }
    });
  });
  document.addEventListener("pointermove", (event) => {
    if (
      window.MemeManagerUI.state.longPressState.emojiItem &&
      typeof event.pointerId === "number" &&
      event.pointerId === window.MemeManagerUI.state.longPressState.pointerId
    ) {
      const offsetX = event.clientX - window.MemeManagerUI.state.longPressState.startX;
      const offsetY = event.clientY - window.MemeManagerUI.state.longPressState.startY;
      const movedDistance = Math.hypot(offsetX, offsetY);
      if (movedDistance > window.MemeManagerUI.state.LONG_PRESS_CANCEL_DISTANCE_PX) {
        window.MemeManagerUI.emoji.cancelLongPress();
        return;
      }

      window.MemeManagerUI.state.longPressState.currentX = event.clientX;
      window.MemeManagerUI.state.longPressState.currentY = event.clientY;

      const elapsed = performance.now() - window.MemeManagerUI.state.longPressState.startTime;
      const progress = Math.min(1, elapsed / window.MemeManagerUI.state.LONG_PRESS_DURATION_MS);
      const remainingSeconds = Math.max(
        1,
        Math.ceil((window.MemeManagerUI.state.LONG_PRESS_DURATION_MS - elapsed) / 1000),
      );
      window.MemeManagerUI.emoji.setLongPressProgress(progress, `${remainingSeconds}s`);
      event.preventDefault();
    }

    if (
      window.MemeManagerUI.state.dragModeState.pointerId !== null &&
      typeof event.pointerId === "number" &&
      event.pointerId === window.MemeManagerUI.state.dragModeState.pointerId
    ) {
      window.MemeManagerUI.emoji.updatePointerDrag(event);
      event.preventDefault();
    }
  });
  document.addEventListener("pointerup", (event) => {
    void window.MemeManagerUI.emoji.handlePointerRelease(event);
  });
  document.addEventListener("pointercancel", (event) => {
    void window.MemeManagerUI.emoji.handlePointerRelease(event);
  });
  document.addEventListener(
    "touchmove",
    (event) => {
      if (window.MemeManagerUI.state.dragModeState.pointerId !== null) {
        event.preventDefault();
      }
    },
    { passive: false },
  );
  document.addEventListener("dragstart", (event) => {
    if (window.MemeManagerUI.emoji.hasActiveDragInteraction() || event.target?.closest?.(".emoji-item")) {
      event.preventDefault();
    }
  });
  document.addEventListener("contextmenu", (event) => {
    if (window.MemeManagerUI.emoji.shouldOpenBatchContextMenu(event)) {
      event.preventDefault();
      window.MemeManagerUI.emoji.openBatchContextMenu(event);
      return;
    }

    window.MemeManagerUI.emoji.closeBatchContextMenu();

    if (window.MemeManagerUI.emoji.hasActiveDragInteraction()) {
      event.preventDefault();
    }
  });
  document.addEventListener("click", (event) => {
    if (!window.MemeManagerUI.state.batchContextMenu || window.MemeManagerUI.state.batchContextMenu.classList.contains("hidden")) {
      return;
    }
    if (event.target.closest("#batch-context-menu")) {
      return;
    }
    window.MemeManagerUI.emoji.closeBatchContextMenu();
  });
  document.addEventListener(
    "scroll",
    () => {
      window.MemeManagerUI.emoji.closeBatchContextMenu();
    },
    true,
  );
  document.addEventListener("selectstart", (event) => {
    if (
      window.MemeManagerUI.emoji.hasActiveDragInteraction() ||
      event.target?.closest?.(".emoji-item") ||
      event.target?.closest?.(".emoji-upload")
    ) {
      event.preventDefault();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && window.MemeManagerUI.state.dragModeState.items.length > 0) {
      window.MemeManagerUI.emoji.clearDragMode();
      window.MemeManagerUI.dialogs.showToast("已退出拖拽模式。", "info", "拖拽模式已关闭");
      return;
    }
    if (event.key === "Escape" && window.MemeManagerUI.state.batchContextMenu) {
      const isBatchContextMenuOpen =
        !window.MemeManagerUI.state.batchContextMenu.classList.contains("hidden");
      if (isBatchContextMenuOpen) {
        window.MemeManagerUI.emoji.closeBatchContextMenu();
        return;
      }
    }
    if (event.key === "Escape" && window.MemeManagerUI.emoji.isCompactViewport()) {
      const isAnyPanelOpen = window.MemeManagerUI.emoji.isConsoleVisible() || window.MemeManagerUI.emoji.isDirectoryVisible();
      if (isAnyPanelOpen) {
        window.MemeManagerUI.emoji.closeAllPanels();
        window.MemeManagerUI.emoji.updatePanelToggleState();
        return;
      }
    }
    if (event.key === "Escape" && window.MemeManagerUI.state.moveTargetModalRoot) {
      const isMoveTargetOpen =
        !window.MemeManagerUI.state.moveTargetModalRoot.classList.contains("hidden");
      if (isMoveTargetOpen) {
        window.MemeManagerUI.emoji.closeMoveTargetModal();
        return;
      }
    }
    if (event.key === "Escape" && window.MemeManagerUI.state.imagePreviewModalRoot) {
      const isPreviewOpen = !window.MemeManagerUI.state.imagePreviewModalRoot.classList.contains("hidden");
      if (isPreviewOpen) {
        window.MemeManagerUI.emoji.closeImagePreview();
        return;
      }
    }
    if (event.key === "Escape" && window.MemeManagerUI.state.categoryEditModalRoot) {
      const isEditOpen = !window.MemeManagerUI.state.categoryEditModalRoot.classList.contains("hidden");
      if (isEditOpen) {
        window.MemeManagerUI.emoji.closeCategoryEditModal();
        return;
      }
    }
    if (event.key === "Escape" && window.MemeManagerUI.state.confirmModalRoot) {
      const isConfirmOpen = !window.MemeManagerUI.state.confirmModalRoot.classList.contains("hidden");
      if (isConfirmOpen) {
        window.MemeManagerUI.dialogs.closeConfirm(false);
        return;
      }
    }
    if (event.key === "Escape" && window.MemeManagerUI.state.dangerModalRoot) {
      const isOpen = !window.MemeManagerUI.state.dangerModalRoot.classList.contains("hidden");
      if (isOpen) {
        window.MemeManagerUI.dialogs.closeDangerConfirm(false);
      }
    }
  });
  document
    .getElementById("add-category-btn")
    .addEventListener("click", function () {
      document.getElementById("add-category-form").style.display = "block";
      this.style.display = "none";
    });
  document
    .getElementById("save-category-btn")
    .addEventListener("click", async function () {
      const categoryName = document
        .getElementById("new-category-name")
        .value.trim();
      const categoryDesc =
        document.getElementById("new-category-description").value.trim() ||
        "请添加描述";

      if (!categoryName) {
        window.MemeManagerUI.dialogs.showToast("请输入类别名称后再保存。", "warning", "缺少类别名称");
        return;
      }

      const saveButton = this;
      window.MemeManagerUI.emoji.setButtonBusy(saveButton, "保存中...");

      try {
        await window.MemeManagerUI.api.apiPost("category/restore", {
          category: categoryName,
          description: categoryDesc,
        });

        document.getElementById("new-category-name").value = "";
        document.getElementById("new-category-description").value = "";
        document.getElementById("add-category-form").style.display = "none";
        document.getElementById("add-category-btn").style.display = "block";
        await window.MemeManagerUI.emoji.refreshUi({ emojis: true, syncStatus: true });
        window.MemeManagerUI.dialogs.showToast(`类别「${categoryName}」已添加。`, "success", "添加成功");
      } catch (error) {
        console.error("添加类别失败:", error);
        window.MemeManagerUI.dialogs.showToast(error.message, "error", "添加失败");
      } finally {
        window.MemeManagerUI.emoji.restoreButton(saveButton);
      }
    });
  window.restoreCategory = window.MemeManagerUI.pack.restoreCategory;
  window.removeFromConfig = window.MemeManagerUI.pack.removeFromConfig;
  window.syncConfig = window.MemeManagerUI.pack.syncConfig;
  window.editCategory = window.MemeManagerUI.emoji.editCategory;
  window.cancelEdit = window.MemeManagerUI.emoji.cancelEdit;
  window.saveCategory = window.MemeManagerUI.emoji.saveCategory;
  window.MemeManagerUI.emoji.syncSidebarLayout();
  window.MemeManagerUI.emoji.updatePanelToggleState();
  window.addEventListener("resize", () => {
    window.MemeManagerUI.emoji.syncSidebarLayout();
    window.MemeManagerUI.emoji.closeBatchContextMenu();
  });
  window.MemeManagerUI.state.exportModeInputs.forEach((input) => {
    input.addEventListener("change", window.MemeManagerUI.pack.updateExportModeAppearance);
  });
  window.MemeManagerUI.state.exportPackDownloadBtn?.addEventListener("click", () => {
    void window.MemeManagerUI.pack.downloadCurrentPack();
  });
  window.MemeManagerUI.state.packImportFile?.addEventListener("change", (event) => {
    const file = event.target?.files?.[0];
    void window.MemeManagerUI.pack.stagePackImport(file);
  });
  ["dragenter", "dragover"].forEach((eventName) => {
    window.MemeManagerUI.state.packImportDropzone?.addEventListener(eventName, (event) => {
      event.preventDefault();
      window.MemeManagerUI.state.packImportDropzone.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach((eventName) => {
    window.MemeManagerUI.state.packImportDropzone?.addEventListener(eventName, (event) => {
      event.preventDefault();
      window.MemeManagerUI.state.packImportDropzone.classList.remove("dragover");
    });
  });
  window.MemeManagerUI.state.packImportDropzone?.addEventListener("drop", (event) => {
    const file = event.dataTransfer?.files?.[0];
    void window.MemeManagerUI.pack.stagePackImport(file);
  });
  window.MemeManagerUI.state.packImportResetBtn?.addEventListener("click", () => {
    window.MemeManagerUI.pack.resetPackImportPreview();
  });
  window.MemeManagerUI.state.packImportConfirmBtn?.addEventListener("click", () => {
    void window.MemeManagerUI.pack.confirmPackImport();
  });
  window.MemeManagerUI.pack.updateExportModeAppearance();
  await window.MemeManagerUI.pack.loadManagePackSwitcher();
  await window.MemeManagerUI.emoji.fetchEmojis();
  window.MemeManagerUI.state.switchManagePackBtn?.addEventListener("click", () => {
    void window.MemeManagerUI.pack.switchManagePack();
  });
  window.MemeManagerUI.state.deleteManagePackBtn?.addEventListener("click", () => {
    void window.MemeManagerUI.pack.deleteCurrentManagePack();
  });
  window.MemeManagerUI.state.initialStatusTimerId = window.setTimeout(() => {
    window.MemeManagerUI.state.initialStatusTimerId = null;
    void window.MemeManagerUI.pack.checkSyncStatus(false);
  }, 180);
}

initApp();
