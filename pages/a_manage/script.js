let manageInitialized = false;
let manageInitializationPromise = null;

async function initializeManageView() {
  await window.AstrBotPluginPage.ready();
  window.AstrBotPluginPage.getContext();

  const state = window.MemeManagerUI.state;
  const emoji = window.MemeManagerUI.emoji;
  const dialogs = window.MemeManagerUI.dialogs;

  state.consoleToggleBtn?.addEventListener("click", () => {
    emoji.toggleConsolePanel();
  });
  state.directoryToggleBtn?.addEventListener("click", () => {
    emoji.toggleDirectoryPanel();
  });
  state.sidebarBackdrop?.addEventListener("click", () => {
    emoji.closeAllPanels();
    emoji.updatePanelToggleState();
  });

  state.confirmModalCancelBtn?.addEventListener("click", () => {
    dialogs.closeConfirm(false);
  });
  state.confirmModalConfirmBtn?.addEventListener("click", () => {
    dialogs.closeConfirm(true);
  });
  state.confirmModalRoot?.addEventListener("click", (event) => {
    if (event.target === state.confirmModalRoot) dialogs.closeConfirm(false);
  });

  state.dangerModalAcknowledge?.addEventListener("change", () => {
    if (state.dangerConfirmStage === "ack" && state.dangerModalAcknowledge.checked) {
      dialogs.startDangerCountdown();
    }
  });
  state.dangerModalCancelBtn?.addEventListener("click", () => {
    dialogs.closeDangerConfirm(false);
  });
  state.dangerModalConfirmBtn?.addEventListener("click", () => {
    if (state.dangerConfirmStage === "ready") dialogs.closeDangerConfirm(true);
  });
  state.dangerModalRoot?.addEventListener("click", (event) => {
    if (event.target === state.dangerModalRoot) dialogs.closeDangerConfirm(false);
  });

  state.categoryEditCancelBtn?.addEventListener("click", () => {
    emoji.closeCategoryEditModal();
  });
  state.categoryEditSaveBtn?.addEventListener("click", () => {
    void emoji.saveCategory();
  });
  state.categoryEditModalRoot?.addEventListener("click", (event) => {
    if (event.target === state.categoryEditModalRoot) emoji.closeCategoryEditModal();
  });
  state.categoryEditDescInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void emoji.saveCategory();
    }
  });

  state.imagePreviewCloseBtn?.addEventListener("click", emoji.closeImagePreview);
  state.imagePreviewOriginalBtn?.addEventListener("click", (event) => {
    event.stopPropagation();
    void emoji.showOriginalPreview();
  });
  state.imagePreviewModalRoot?.addEventListener("click", (event) => {
    if (event.target === state.imagePreviewModalRoot ||
        event.target?.classList?.contains("image-preview-stage")) {
      emoji.closeImagePreview();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (state.imagePreviewModalRoot && !state.imagePreviewModalRoot.classList.contains("hidden")) {
      emoji.closeImagePreview();
      return;
    }
    if (state.categoryEditModalRoot && !state.categoryEditModalRoot.classList.contains("hidden")) {
      emoji.closeCategoryEditModal();
      return;
    }
    if (state.confirmModalRoot && !state.confirmModalRoot.classList.contains("hidden")) {
      dialogs.closeConfirm(false);
      return;
    }
    if (state.dangerModalRoot && !state.dangerModalRoot.classList.contains("hidden")) {
      dialogs.closeDangerConfirm(false);
      return;
    }
    if (emoji.isCompactViewport()) {
      emoji.closeAllPanels();
      emoji.updatePanelToggleState();
    }
  });

  window.addEventListener("resize", emoji.syncSidebarLayout);
  window.removeFromConfig = window.MemeManagerUI.pack.removeFromConfig;
  window.syncConfig = window.MemeManagerUI.pack.syncConfig;
  window.editCategory = emoji.editCategory;
  window.cancelEdit = emoji.cancelEdit;
  window.saveCategory = emoji.saveCategory;

  emoji.syncSidebarLayout();
  await window.MemeManagerUI.pack.loadManagePackSwitcher();
  await emoji.fetchEmojis();
  state.switchManagePackBtn?.addEventListener("click", () => {
    void window.MemeManagerUI.pack.switchManagePack();
  });
  state.deleteManagePackBtn?.addEventListener("click", () => {
    void window.MemeManagerUI.pack.deleteCurrentManagePack();
  });
  state.initialStatusTimerId = window.setTimeout(() => {
    state.initialStatusTimerId = null;
    void window.MemeManagerUI.pack.checkSyncStatus(false);
  }, 180);
}

async function initManageView() {
  if (manageInitialized) return;
  if (!manageInitializationPromise) {
    manageInitializationPromise = initializeManageView()
      .then(() => {
        manageInitialized = true;
      })
      .finally(() => {
        manageInitializationPromise = null;
      });
  }
  return manageInitializationPromise;
}

async function activateManageView() {
  if (!manageInitialized) return;
  const requestedPackId = String(
    new URLSearchParams(window.location.search).get("managed_pack_id") || "",
  ).trim();
  const state = window.MemeManagerUI.state;
  if (!requestedPackId || requestedPackId === state.activeManagePackId) return;

  if (!state.managePacksById.has(requestedPackId)) {
    await window.MemeManagerUI.pack.loadManagePackSwitcher(requestedPackId);
  } else {
    state.managePackSelect.value = requestedPackId;
    state.activeManagePackId = requestedPackId;
    state.managedPackIdFromUrl = requestedPackId;
  }
  if (state.activeManagePackId !== requestedPackId) return;

  window.MemeManagerUI.emoji.closeImagePreview();
  await Promise.all([
    window.MemeManagerUI.emoji.fetchEmojis(),
    window.MemeManagerUI.pack.checkSyncStatus(false),
  ]);
}

window.MemeManagerUI = window.MemeManagerUI || {};
window.MemeManagerUI.initManageView = initManageView;
window.MemeManagerUI.activateManageView = activateManageView;
