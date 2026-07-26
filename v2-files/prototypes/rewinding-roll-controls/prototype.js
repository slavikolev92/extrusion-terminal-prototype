(() => {
  const assets = window.__REWINDING_PROTOTYPE_ASSETS__ || {};
  const inputPanel = document.querySelector(".input-panel");
  const panelHead = inputPanel?.querySelector(":scope > .panel-head");
  const rollHead = inputPanel?.querySelector(".roll-head");
  const rollRows = [...(inputPanel?.querySelectorAll(".roll-row[data-roll-id]") || [])];
  const correctionActions = inputPanel?.querySelector("[data-roll-correction-actions]");
  const rollBody = inputPanel?.querySelector("[data-roll-body]");

  if (!inputPanel || !panelHead || !rollHead || !correctionActions || !rollBody) {
    return;
  }

  document.addEventListener("submit", (event) => event.preventDefault());

  const formatWeight = (value) => {
    const parsed = Number(String(value).trim());
    return Number.isFinite(parsed) ? parsed.toFixed(1) : String(value).trim();
  };

  const configureRollPresentation = () => {
    const entryLabels = [
      ["[data-new-roll-autofocus]", "Ролка"],
      ["[data-current-tare-input]", "Шпула"],
      ["[data-current-pallet-input]", "Палет"],
    ];
    for (const [selector, text] of entryLabels) {
      const input = inputPanel.querySelector(selector);
      const label = input?.closest("label");
      const caption = label?.querySelector(".field-label");
      if (!label || !caption) continue;
      label.classList.add("prototype-floating-field");
      caption.textContent = text;
      if (
        selector === "[data-current-tare-input]"
        && window.__REWINDING_PROTOTYPE_STANDALONE__ === true
      ) {
        input.value = formatWeight(input.value);
      }
    }

    const headingCells = [...rollHead.children].filter(
      (cell) => !cell.classList.contains("roll-edit-heading"),
    );
    const findHeading = (pattern) => headingCells.find((cell) => pattern.test(cell.textContent.trim()));
    const orderedHeadings = [
      findHeading(/^№$/),
      findHeading(/^Бруто/),
      findHeading(/^Шпула/),
      findHeading(/^Нето/),
      findHeading(/^Палет/),
    ];
    if (orderedHeadings.every(Boolean)) {
      const labels = ["№", "Бруто", "Шпула", "Нето", "Палет"];
      orderedHeadings.forEach((cell, index) => {
        cell.textContent = labels[index];
        rollHead.append(cell);
      });
    }

    for (const row of rollRows) {
      const numberCell = row.firstElementChild;
      const palletCell = row.querySelector('[data-roll-display="pallet"]')?.closest(".roll-weight-cell");
      const grossCell = row.querySelector('[data-roll-display="gross"]')?.closest(".roll-weight-cell");
      const tareCell = row.querySelector('[data-roll-display="tare"]')?.closest(".roll-weight-cell");
      const knownCells = new Set([numberCell, palletCell, grossCell, tareCell]);
      const netCell = [...row.children].find(
        (cell) => !knownCells.has(cell) && !cell.classList.contains("roll-edit-cell"),
      );
      if (!numberCell || !palletCell || !grossCell || !tareCell || !netCell) continue;

      numberCell.classList.add("roll-number-cell");
      netCell.classList.add("roll-net-cell");
      netCell.dataset.rollDisplay = "net";

      for (const kind of ["gross", "tare"]) {
        const display = row.querySelector(`[data-roll-display="${kind}"]`);
        const input = display?.parentElement?.querySelector("[data-roll-correction-input]");
        if (display) display.textContent = formatWeight(display.textContent);
        if (input) input.value = formatWeight(input.value);
      }
      netCell.textContent = formatWeight(netCell.textContent);

      row.append(numberCell, grossCell, tareCell, netCell, palletCell);
    }
  };

  configureRollPresentation();

  const iconImage = (source, alt = "") => {
    const image = document.createElement("img");
    image.src = source || "";
    image.alt = alt;
    image.setAttribute("aria-hidden", alt ? "false" : "true");
    return image;
  };

  const closeModal = (modal) => {
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
  };

  const openModal = (modal, focusTarget) => {
    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
    window.setTimeout(() => focusTarget?.focus(), 0);
  };

  const makeModal = ({ id, title, body }) => {
    let modal = document.getElementById(id);
    if (modal) return modal;
    modal = document.createElement("div");
    modal.className = "finish-confirm-modal";
    modal.id = id;
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
    modal.innerHTML = `
      <div class="finish-confirm-panel" role="dialog" aria-modal="true" aria-labelledby="${id}-title">
        <h2 class="finish-confirm-title" id="${id}-title">${title}</h2>
        ${body}
      </div>
    `;
    document.body.append(modal);
    modal.addEventListener("click", (event) => {
      if (event.target === modal) closeModal(modal);
    });
    return modal;
  };

  let rewindingCount = 0;
  let rollChangeSeconds = 0;
  let rollChangeTimer = null;

  if (!panelHead.querySelector("[data-roll-secondary-actions]")) {
    const existingMenu = document.querySelector(".topbar .menu");
    existingMenu?.remove();

    const secondaryActions = document.createElement("div");
    secondaryActions.className = "roll-secondary-actions";
    secondaryActions.dataset.rollSecondaryActions = "true";

    const rewindingButton = document.createElement("button");
    rewindingButton.className = "roll-secondary-button";
    rewindingButton.type = "button";
    rewindingButton.dataset.rewindingButton = "true";
    rewindingButton.append(iconImage(assets.rewinding));
    rewindingButton.append(document.createElement("span"));
    rewindingButton.querySelector("span").textContent = "Пренавиване";

    const rollChangeButton = document.createElement("button");
    rollChangeButton.className = "roll-secondary-button";
    rollChangeButton.type = "button";
    rollChangeButton.dataset.rollChangeButton = "true";
    rollChangeButton.append(iconImage(assets.clock));
    rollChangeButton.append(document.createElement("span"));
    rollChangeButton.querySelector("span").textContent = "Смяна на ролка";

    secondaryActions.append(rewindingButton, rollChangeButton);
    panelHead.append(secondaryActions);

    const rewindingModal = makeModal({
      id: "prototype-rewinding-modal",
      title: "Ролки за пренавиване",
      body: `
        <label class="prototype-modal-field">
          <span>Брой ролки</span>
          <input type="number" min="0" step="1" inputmode="numeric" data-rewinding-count placeholder="0">
        </label>
        <p class="prototype-modal-hint">Броят е само информативен и може да бъде променен.</p>
        <p class="prototype-modal-error" data-rewinding-error hidden>Въведете цяло положително число или изчистете стойността.</p>
        <div class="finish-confirm-actions">
          <button class="finish-confirm-secondary" type="button" data-rewinding-cancel>Отказ</button>
          <button class="finish-confirm-primary prototype-modal-primary" type="button" data-rewinding-save>Запиши</button>
        </div>
      `,
    });
    const rewindingInput = rewindingModal.querySelector("[data-rewinding-count]");
    const rewindingError = rewindingModal.querySelector("[data-rewinding-error]");
    rewindingButton.addEventListener("click", () => {
      rewindingInput.value = rewindingCount > 0 ? String(rewindingCount) : "";
      rewindingError.hidden = true;
      openModal(rewindingModal, rewindingInput);
    });
    rewindingModal.querySelector("[data-rewinding-cancel]").addEventListener("click", () => closeModal(rewindingModal));
    rewindingModal.querySelector("[data-rewinding-save]").addEventListener("click", () => {
      const rawValue = rewindingInput.value.trim();
      if (rawValue === "" || rawValue === "0") {
        rewindingCount = 0;
      } else {
        const parsed = Number(rawValue);
        if (!Number.isInteger(parsed) || parsed <= 0) {
          rewindingError.hidden = false;
          rewindingInput.focus();
          return;
        }
        rewindingCount = parsed;
      }
      rewindingButton.querySelector("span").textContent = rewindingCount > 0 ? `Пренавиване: ${rewindingCount}` : "Пренавиване";
      rewindingButton.classList.toggle("is-marked", rewindingCount > 0);
      closeModal(rewindingModal);
    });

    const rollChangeModal = makeModal({
      id: "prototype-roll-change-modal",
      title: "Интервал за смяна на ролка",
      body: `
        <label class="prototype-modal-field">
          <span>Часове</span>
          <input type="number" min="0" max="23" step="1" inputmode="numeric" data-roll-change-hours value="2">
        </label>
        <label class="prototype-modal-field">
          <span>Минути</span>
          <input type="number" min="0" max="59" step="1" inputmode="numeric" data-roll-change-minutes value="30">
        </label>
        <p class="prototype-modal-error" data-roll-change-error hidden>Въведете интервал, по-голям от нула.</p>
        <div class="finish-confirm-actions">
          <button class="finish-confirm-secondary" type="button" data-roll-change-cancel>Отказ</button>
          <button class="finish-confirm-primary prototype-modal-primary" type="button" data-roll-change-start>Започни</button>
        </div>
      `,
    });
    const hoursInput = rollChangeModal.querySelector("[data-roll-change-hours]");
    const minutesInput = rollChangeModal.querySelector("[data-roll-change-minutes]");
    const rollChangeError = rollChangeModal.querySelector("[data-roll-change-error]");
    const renderRollChange = () => {
      const hours = Math.floor(rollChangeSeconds / 3600);
      const minutes = Math.floor((rollChangeSeconds % 3600) / 60);
      const seconds = rollChangeSeconds % 60;
      const display = [hours, minutes, seconds].map((value) => String(value).padStart(2, "0")).join(":");
      rollChangeButton.querySelector("span").textContent = rollChangeSeconds > 0 ? `Смяна: ${display}` : "Смяна на ролка";
      rollChangeButton.classList.toggle("is-running", rollChangeSeconds > 0);
    };
    rollChangeButton.addEventListener("click", () => {
      rollChangeError.hidden = true;
      openModal(rollChangeModal, hoursInput);
    });
    rollChangeModal.querySelector("[data-roll-change-cancel]").addEventListener("click", () => closeModal(rollChangeModal));
    rollChangeModal.querySelector("[data-roll-change-start]").addEventListener("click", () => {
      const hours = Number(hoursInput.value);
      const minutes = Number(minutesInput.value);
      if (!Number.isInteger(hours) || !Number.isInteger(minutes) || hours < 0 || minutes < 0 || minutes > 59 || hours + minutes === 0) {
        rollChangeError.hidden = false;
        return;
      }
      rollChangeSeconds = hours * 3600 + minutes * 60;
      window.clearInterval(rollChangeTimer);
      renderRollChange();
      rollChangeTimer = window.setInterval(() => {
        rollChangeSeconds = Math.max(rollChangeSeconds - 1, 0);
        renderRollChange();
        if (rollChangeSeconds === 0) window.clearInterval(rollChangeTimer);
      }, 1000);
      closeModal(rollChangeModal);
    });
  }

  if (!rollHead.querySelector(".roll-edit-heading")) {
    const heading = document.createElement("div");
    heading.className = "roll-edit-heading";
    heading.setAttribute("aria-label", "Редакция");
    heading.textContent = "";
    rollHead.append(heading);
  }

  const closeRowEdit = () => {
    for (const row of rollRows) {
      row.classList.remove("is-editing");
      for (const display of row.querySelectorAll(".roll-display-value")) display.hidden = false;
      for (const input of row.querySelectorAll("[data-roll-correction-input]")) {
        input.hidden = true;
        input.disabled = true;
      }
    }
    correctionActions.hidden = true;
    correctionActions.classList.remove("prototype-row-actions");
    rollBody.classList.remove("roll-correction-mode");
  };

  const deleteModal = makeModal({
    id: "prototype-delete-modal",
    title: "Изтриване на ролка",
    body: `
      <div class="prototype-delete-confirmation">
        <p class="finish-confirm-body" data-delete-message></p>
        <label class="prototype-modal-field">
          <span>Потвърдете номера на ролката</span>
          <input type="number" min="1" step="1" inputmode="numeric" data-delete-confirmation>
        </label>
        <p class="prototype-modal-error" data-delete-error hidden>Номерът не съвпада.</p>
        <div class="finish-confirm-actions">
          <button class="finish-confirm-secondary" type="button" data-delete-cancel>Отказ</button>
          <button class="finish-confirm-primary" type="button" data-delete-submit>Изтрий</button>
        </div>
      </div>
    `,
  });
  let rowPendingDelete = null;
  deleteModal.querySelector("[data-delete-cancel]").addEventListener("click", () => closeModal(deleteModal));
  deleteModal.querySelector("[data-delete-submit]").addEventListener("click", () => {
    if (!rowPendingDelete) return;
    const expected = rowPendingDelete.querySelector(":scope > div")?.textContent.trim();
    const supplied = deleteModal.querySelector("[data-delete-confirmation]").value.trim();
    if (supplied !== expected) {
      deleteModal.querySelector("[data-delete-error]").hidden = false;
      return;
    }
    rowPendingDelete.remove();
    closeModal(deleteModal);
    closeRowEdit();
    [...inputPanel.querySelectorAll(".roll-row[data-roll-id]")].forEach((row, index) => {
      row.querySelector(":scope > div").textContent = String(index + 1);
    });
  });

  const openRowEdit = (row) => {
    closeRowEdit();
    row.classList.add("is-editing");
    for (const display of row.querySelectorAll(".roll-display-value")) display.hidden = true;
    for (const input of row.querySelectorAll("[data-roll-correction-input]")) {
      input.hidden = false;
      input.disabled = false;
    }
    const rollNumber = row.querySelector(":scope > div")?.textContent.trim() || "-";
    correctionActions.innerHTML = `
      <div class="roll-correction-message">Редакция на ролка №${rollNumber}</div>
      <div class="roll-correction-buttons">
        <button class="prototype-delete-button" type="button" data-prototype-delete>Изтрий</button>
        <button class="prototype-cancel-button" type="button" data-prototype-cancel>Отказ</button>
        <button class="prototype-save-button" type="button" data-prototype-save>Запиши</button>
      </div>
      <div class="roll-correction-error-slot field-error-slot" data-prototype-row-error></div>
    `;
    correctionActions.hidden = false;
    correctionActions.classList.add("prototype-row-actions");
    rollBody.classList.add("roll-correction-mode");
    correctionActions.querySelector("[data-prototype-cancel]").addEventListener("click", closeRowEdit);
    correctionActions.querySelector("[data-prototype-save]").addEventListener("click", () => {
      for (const cell of row.querySelectorAll(".roll-weight-cell")) {
        const display = cell.querySelector(".roll-display-value");
        const input = cell.querySelector("[data-roll-correction-input]");
        if (!display || !input) continue;
        const rawValue = input.value.trim();
        display.textContent = ["gross", "tare"].includes(display.dataset.rollDisplay)
          ? formatWeight(rawValue)
          : rawValue || "-";
      }
      const gross = Number(row.querySelector('[name^="gross_weight__"]')?.value);
      const tare = Number(row.querySelector('[name^="tare_weight__"]')?.value);
      const net = row.querySelector('[data-roll-display="net"]');
      if (net && Number.isFinite(gross) && Number.isFinite(tare)) {
        net.textContent = formatWeight(gross - tare);
      }
      closeRowEdit();
    });
    correctionActions.querySelector("[data-prototype-delete]").addEventListener("click", () => {
      rowPendingDelete = row;
      deleteModal.querySelector("[data-delete-message]").textContent = `Сигурни ли сте, че искате да изтриете ролка №${rollNumber}?`;
      deleteModal.querySelector("[data-delete-confirmation]").value = "";
      deleteModal.querySelector("[data-delete-error]").hidden = true;
      openModal(deleteModal, deleteModal.querySelector("[data-delete-confirmation]"));
    });
    row.querySelector("[data-roll-correction-input]")?.focus();
  };

  for (const row of rollRows) {
    if (row.querySelector(".roll-edit-cell")) continue;
    const editCell = document.createElement("div");
    editCell.className = "roll-edit-cell";
    const editButton = document.createElement("button");
    editButton.className = "roll-edit-button";
    editButton.type = "button";
    editButton.setAttribute("aria-label", `Редактирай ролка ${row.querySelector(":scope > div")?.textContent.trim() || ""}`);
    editButton.append(iconImage(assets.pencil));
    editButton.addEventListener("click", () => openRowEdit(row));
    editCell.append(editButton);
    row.append(editCell);
  }

  inputPanel.querySelector(".roll-delete-panel")?.remove();
  closeRowEdit();
})();
