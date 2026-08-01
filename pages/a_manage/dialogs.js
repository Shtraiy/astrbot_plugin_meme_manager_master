window.MemeManagerUI = window.MemeManagerUI || {};
window.MemeManagerUI.dialogs = window.MemeManagerUI.dialogs || {};
window.MemeManagerUI.dialogs.showToast = function (message, type = "info", title = "提示", duration = 3200) {
    if (!window.MemeManagerUI.state.toastContainer) {
      return;
    }

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;

    const content = document.createElement("div");
    content.className = "toast-content";

    const titleElement = document.createElement("p");
    titleElement.className = "toast-title";
    titleElement.textContent = title;

    const messageElement = document.createElement("p");
    messageElement.className = "toast-message";
    messageElement.textContent = message;

    content.appendChild(titleElement);
    content.appendChild(messageElement);
    toast.appendChild(content);
    window.MemeManagerUI.state.toastContainer.appendChild(toast);

    window.setTimeout(() => {
      toast.remove();
    }, duration);
  }
window.MemeManagerUI.dialogs.closeConfirm = function (result) {
    if (window.MemeManagerUI.state.confirmModalRoot) {
      window.MemeManagerUI.state.confirmModalRoot.classList.add("hidden");
      window.MemeManagerUI.state.confirmModalRoot.setAttribute("aria-hidden", "true");
    }
    if (window.MemeManagerUI.state.confirmModalConfirmBtn) {
      window.MemeManagerUI.state.confirmModalConfirmBtn.classList.remove("danger");
      window.MemeManagerUI.state.confirmModalConfirmBtn.textContent = "确认";
    }
    if (window.MemeManagerUI.state.confirmResolver) {
      const resolver = window.MemeManagerUI.state.confirmResolver;
      window.MemeManagerUI.state.confirmResolver = null;
      resolver(result);
    }
  }
window.MemeManagerUI.dialogs.showConfirm = function ({
    title,
    description,
    confirmLabel = "确认",
    confirmClassName = "",
  }) {
    if (
      !window.MemeManagerUI.state.confirmModalRoot ||
      !window.MemeManagerUI.state.confirmModalTitle ||
      !window.MemeManagerUI.state.confirmModalDescription ||
      !window.MemeManagerUI.state.confirmModalConfirmBtn
    ) {
      return Promise.resolve(confirm(`${title}\n\n${description}`));
    }

    window.MemeManagerUI.state.confirmModalTitle.textContent = title;
    window.MemeManagerUI.state.confirmModalDescription.textContent = description;
    window.MemeManagerUI.state.confirmModalConfirmBtn.textContent = confirmLabel;
    window.MemeManagerUI.state.confirmModalConfirmBtn.classList.toggle(
      "danger",
      confirmClassName.includes("danger"),
    );
    window.MemeManagerUI.state.confirmModalRoot.classList.remove("hidden");
    window.MemeManagerUI.state.confirmModalRoot.setAttribute("aria-hidden", "false");

    return new Promise((resolve) => {
      window.MemeManagerUI.state.confirmResolver = resolve;
    });
  }
window.MemeManagerUI.dialogs.resetDangerConfirmState = function () {
    if (window.MemeManagerUI.state.dangerConfirmTimer) {
      clearInterval(window.MemeManagerUI.state.dangerConfirmTimer);
      window.MemeManagerUI.state.dangerConfirmTimer = null;
    }
    window.MemeManagerUI.state.dangerConfirmConfig = null;
    window.MemeManagerUI.state.dangerConfirmStage = "ack";
    if (window.MemeManagerUI.state.dangerModalAcknowledge) {
      window.MemeManagerUI.state.dangerModalAcknowledge.checked = false;
      window.MemeManagerUI.state.dangerModalAcknowledge.disabled = false;
    }
    if (window.MemeManagerUI.state.dangerModalStageText) {
      window.MemeManagerUI.state.dangerModalStageText.textContent =
        "请先勾选已理解，勾选后会自动开始 5 秒倒计时。";
    }
    if (window.MemeManagerUI.state.dangerModalConfirmBtn) {
      window.MemeManagerUI.state.dangerModalConfirmBtn.disabled = true;
      window.MemeManagerUI.state.dangerModalConfirmBtn.textContent = "请先勾选上方选项";
    }
  }
window.MemeManagerUI.dialogs.closeDangerConfirm = function (result) {
    if (window.MemeManagerUI.state.dangerModalRoot) {
      window.MemeManagerUI.state.dangerModalRoot.classList.add("hidden");
      window.MemeManagerUI.state.dangerModalRoot.setAttribute("aria-hidden", "true");
    }
    window.MemeManagerUI.dialogs.resetDangerConfirmState();
    if (window.MemeManagerUI.state.dangerConfirmResolver) {
      const resolver = window.MemeManagerUI.state.dangerConfirmResolver;
      window.MemeManagerUI.state.dangerConfirmResolver = null;
      resolver(result);
    }
  }
window.MemeManagerUI.dialogs.startDangerCountdown = function () {
    if (window.MemeManagerUI.state.dangerConfirmStage !== "ack" || !window.MemeManagerUI.state.dangerConfirmConfig) {
      return;
    }

    const countdown = window.MemeManagerUI.state.dangerConfirmConfig?.countdown ?? 5;
    let remaining = countdown;

    window.MemeManagerUI.state.dangerConfirmStage = "countdown";
    if (window.MemeManagerUI.state.dangerModalAcknowledge) {
      window.MemeManagerUI.state.dangerModalAcknowledge.disabled = true;
    }
    if (window.MemeManagerUI.state.dangerModalStageText) {
      window.MemeManagerUI.state.dangerModalStageText.textContent = `安全等待中，还需 ${remaining} 秒，倒计时结束后才可执行。`;
    }
    if (window.MemeManagerUI.state.dangerModalConfirmBtn) {
      window.MemeManagerUI.state.dangerModalConfirmBtn.disabled = true;
      window.MemeManagerUI.state.dangerModalConfirmBtn.textContent = `等待 ${remaining} 秒`;
    }

    window.MemeManagerUI.state.dangerConfirmTimer = setInterval(() => {
      remaining -= 1;
      if (remaining > 0) {
        window.MemeManagerUI.state.dangerModalStageText.textContent = `安全等待中，还需 ${remaining} 秒，倒计时结束后才可执行。`;
        window.MemeManagerUI.state.dangerModalConfirmBtn.textContent = `等待 ${remaining} 秒`;
        return;
      }

      clearInterval(window.MemeManagerUI.state.dangerConfirmTimer);
      window.MemeManagerUI.state.dangerConfirmTimer = null;
      window.MemeManagerUI.state.dangerConfirmStage = "ready";
      window.MemeManagerUI.state.dangerModalStageText.textContent =
        "5 秒倒计时已结束，请点击下方按钮执行。";
      window.MemeManagerUI.state.dangerModalConfirmBtn.disabled = false;
      window.MemeManagerUI.state.dangerModalConfirmBtn.textContent = window.MemeManagerUI.state.dangerConfirmConfig.actionLabel;
    }, 1000);
  }
window.MemeManagerUI.dialogs.showDangerConfirm = function ({
    title,
    description,
    actionLabel,
    countdown = 5,
  }) {
    if (
      !window.MemeManagerUI.state.dangerModalRoot ||
      !window.MemeManagerUI.state.dangerModalTitle ||
      !window.MemeManagerUI.state.dangerModalDescription ||
      !window.MemeManagerUI.state.dangerModalConfirmBtn
    ) {
      return Promise.resolve(
        confirm(`${title}\n\n${description}\n\n确认要继续执行吗？`),
      );
    }

    window.MemeManagerUI.dialogs.resetDangerConfirmState();
    window.MemeManagerUI.state.dangerConfirmConfig = { actionLabel, countdown };
    window.MemeManagerUI.state.dangerModalTitle.textContent = title;
    window.MemeManagerUI.state.dangerModalDescription.textContent = description;
    if (window.MemeManagerUI.state.dangerModalStageText) {
      window.MemeManagerUI.state.dangerModalStageText.textContent = `请先勾选已理解，勾选后会自动开始 ${countdown} 秒倒计时。倒计时结束后才可执行。`;
    }
    if (window.MemeManagerUI.state.dangerModalConfirmBtn) {
      window.MemeManagerUI.state.dangerModalConfirmBtn.textContent = "请先勾选上方选项";
      window.MemeManagerUI.state.dangerModalConfirmBtn.disabled = true;
    }
    window.MemeManagerUI.state.dangerModalRoot.classList.remove("hidden");
    window.MemeManagerUI.state.dangerModalRoot.setAttribute("aria-hidden", "false");

    return new Promise((resolve) => {
      window.MemeManagerUI.state.dangerConfirmResolver = resolve;
    });
  }
