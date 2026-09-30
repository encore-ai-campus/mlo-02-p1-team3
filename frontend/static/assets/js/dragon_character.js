(() => {
  const mascot = document.querySelector("#usimChatMascot");
  const panelMascot = document.querySelector("#usimChatPanelMascot");
  const levelLabel = document.querySelector("#usimChatLevel");
  const stageLabel = document.querySelector("#usimChatStage");
  const modal = document.querySelector("#dragonPickerModal");
  const openButton = document.querySelector("#dragonPickerOpen");
  const designGrid = document.querySelector("#dragonDesignGrid");
  const stageStrip = document.querySelector("#dragonStageStrip");
  const help = document.querySelector("#dragonPickerHelp");
  const message = document.querySelector("#dragonPickerMessage");
  const closeButtons = document.querySelectorAll("[data-dragon-close]");
  const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || "";
  let state = null;

  const apply = payload => {
    state = payload;
    [mascot, panelMascot].forEach(image => {
      if (!image || !payload.image_url) return;
      image.src = payload.image_url;
      image.dataset.dragonSrc = payload.image_url;
      image.alt = `우심이 ${payload.stage_label || "캐릭터"}`;
    });
    if (levelLabel) levelLabel.textContent = `Lv.${payload.level} · ${payload.stage_label}`;
    if (stageLabel) stageLabel.textContent = `Lv.${payload.level} · ${payload.stage_label}`;
    renderModal(payload);
  };

  const renderModal = payload => {
    if (!designGrid || !stageStrip) return;
    stageStrip.innerHTML = (payload.stage_images || []).map(stage => `
      <div class="dragon-stage-card ${payload.image_key === stage.key ? "is-current" : ""}">
        <img src="${stage.image_url}" alt="${stage.label}">
        <span>Lv.${stage.min_level} · ${stage.label}</span>
      </div>`).join("");
    designGrid.innerHTML = (payload.options || []).map(option => {
      const locked = option.locked;
      const price = option.price ? `${option.price.toLocaleString()}원` : "무료";
      return `<button type="button" class="dragon-design-card ${option.selected ? "is-selected" : ""} ${locked ? "is-locked" : ""}" data-dragon-design="${option.key}" ${locked ? "disabled" : ""}>
        <span class="dragon-design-media"><img src="${option.image_url}" alt="${option.label}"></span>
        <strong>${option.label}</strong><small>${locked ? (payload.level < 40 ? "Lv.40부터 선택" : `잠금 · ${price}`) : "선택 가능 · 무료"}</small>
      </button>`;
    }).join("");
    if (help) help.textContent = payload.level < 40
      ? `현재 Lv.${payload.level} · Lv.40부터 최종 우심이 디자인을 선택할 수 있어요.`
      : "최종 우심이 디자인을 모두 무료로 선택할 수 있어요.";
    designGrid.querySelectorAll("[data-dragon-design]").forEach(button => button.addEventListener("click", () => save(button.dataset.dragonDesign)));
  };

  const open = () => { if (modal) { modal.hidden = false; document.body.classList.add("dragon-picker-open"); openButton?.setAttribute("aria-expanded", "true"); } };
  const close = () => { if (modal) { modal.hidden = true; document.body.classList.remove("dragon-picker-open"); openButton?.setAttribute("aria-expanded", "false"); } };
  const save = async design => {
    if (!message) return;
    message.textContent = "우심이 정보를 저장하고 있어요...";
    try {
      const response = await fetch("/api/dragon-character/", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() }, body: JSON.stringify({ design }) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) { message.textContent = data.error || "현재는 선택할 수 없는 우심이예요."; return; }
      apply(data);
      message.textContent = "우심이를 변경했어요.";
      setTimeout(close, 450);
    } catch (_) { message.textContent = "저장에 실패했어요. 기존 우심이는 그대로 유지됩니다."; }
  };

  openButton?.addEventListener("click", open);
  closeButtons.forEach(button => button.addEventListener("click", close));
  document.addEventListener("keydown", event => { if (event.key === "Escape" && modal && !modal.hidden) close(); });
  fetch("/api/dragon-character/", { credentials: "same-origin" })
    .then(response => response.ok ? response.json() : null)
    .then(data => data && apply(data))
    .catch(() => {});
  window.USIMUNKKA_DRAGON = { refresh: () => fetch("/api/dragon-character/", { credentials: "same-origin" }).then(r => r.json()).then(apply) };
})();
