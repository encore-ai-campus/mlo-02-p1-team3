(() => {
  const dock = document.querySelector("#usimChatDock");
  const panel = document.querySelector("#usimChatPanel");
  const launcher = document.querySelector("#usimChatLauncher");
  const prompt = document.querySelector("#usimChatPrompt");
  const promptCopy = prompt?.querySelector(".usim-chat-bubble-copy");
  const promptClose = document.querySelector("#usimChatPromptClose");
  const mascot = document.querySelector("#usimChatMascot");
  const closeButton = document.querySelector("#usimChatClose");
  const clearButton = document.querySelector("#usimChatClear");
  const form = document.querySelector("#usimChatForm");
  const input = document.querySelector("#usimChatInput");
  const sendButton = document.querySelector("#usimChatSend");
  const messages = document.querySelector("#usimChatMessages");
  const chips = document.querySelectorAll(".usim-chat-chip");
  const shell = document.querySelector(".character-theme-shell.mini-shell") || document.querySelector(".mini-shell");
  if (!dock || !panel || !launcher || !prompt || !promptCopy || !mascot || !form || !input || !messages) return;

  const app = window.USIMUNKKA;
  let busy = false;
  let greeted = false;
  let turnIndex = 0;
  let currentPose = "wave";
  let promptTimer = null;
  const poses = ["idle", "wave", "run", "tie"];

  const getProfile = () => {
    try { return app?.getProfile?.() || {}; } catch (_) { return {}; }
  };
  const gender = () => getProfile().avatar_gender === "female" ? "female" : "male";
  const poseSource = pose => {
    if (mascot.dataset.dragonSrc) return mascot.dataset.dragonSrc;
    const g = gender();
    const key = `${g}${pose.charAt(0).toUpperCase()}${pose.slice(1)}Src`;
    const generic = `${g.charAt(0).toUpperCase()}${g.slice(1)}Src`;
    return mascot.dataset[key] || mascot.dataset[generic] || mascot.dataset.defaultSrc || mascot.src;
  };
  const setPose = pose => {
    currentPose = poses.includes(pose) ? pose : "idle";
    const src = poseSource(currentPose);
    if (src) mascot.src = src;
    dock.dataset.pose = currentPose;
  };
  const truncate = (value, max = 58) => {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    if (!text) return "";
    return text.length > max ? `${text.slice(0, max - 1)}…` : text;
  };
  const formatAssistantText = value => {
    const escaped = String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
    return escaped
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\n/g, "<br>");
  };
  const hidePrompt = () => {
    if (promptTimer) clearTimeout(promptTimer);
    promptTimer = null;
    prompt.classList.remove("is-visible");
  };
  const showPrompt = (text, duration = 4800) => {
    promptCopy.textContent = truncate(text, 54) || "오늘 운동, 나한테 물어볼래?";
    prompt.classList.add("is-visible");
    if (promptTimer) clearTimeout(promptTimer);
    if (duration > 0) promptTimer = window.setTimeout(hidePrompt, duration);
  };
  const DOCK_POSITION_KEY = "usim_chat_dock_position_v1";
  let dragState = null;
  let suppressNextClick = false;

  const clampDockPosition = (left, top) => {
    const margin = 4;
    const maxLeft = Math.max(margin, window.innerWidth - dock.offsetWidth - margin);
    const maxTop = Math.max(margin, window.innerHeight - dock.offsetHeight - margin);
    return {
      left: Math.min(Math.max(margin, left), maxLeft),
      top: Math.min(Math.max(margin, top), maxTop),
    };
  };
  const applyDockPosition = (left, top, persist = true) => {
    const position = clampDockPosition(left, top);
    dock.style.left = `${Math.round(position.left)}px`;
    dock.style.top = `${Math.round(position.top)}px`;
    dock.style.right = "auto";
    dock.style.bottom = "auto";
    dock.dataset.moved = "1";
    if (persist) {
      try { localStorage.setItem(DOCK_POSITION_KEY, JSON.stringify(position)); } catch (_) {}
    }
  };
  const restoreDockPosition = () => {
    try {
      const saved = JSON.parse(localStorage.getItem(DOCK_POSITION_KEY) || "null");
      if (saved && Number.isFinite(saved.left) && Number.isFinite(saved.top)) {
        applyDockPosition(saved.left, saved.top, false);
      }
    } catch (_) {}
  };
  const positionPanelFromDock = () => {
    const rect = launcher.getBoundingClientRect();
    const width = Math.min(286, Math.max(240, window.innerWidth - 12));
    const height = Math.min(400, Math.max(300, window.innerHeight * 0.5));
    const left = Math.min(Math.max(6, rect.left + rect.width - width), window.innerWidth - width - 6);
    let top = rect.top - height - 12;
    if (top < 8) top = Math.min(window.innerHeight - height - 8, rect.bottom + 12);
    top = Math.max(8, top);
    const actualHeight = Math.max(240, Math.min(height, window.innerHeight - top - 8));
    panel.style.left = `${Math.round(left)}px`;
    panel.style.right = "auto";
    panel.style.top = `${Math.round(top)}px`;
    panel.style.bottom = "auto";
    panel.style.width = `${Math.round(width)}px`;
    panel.style.height = `${Math.round(actualHeight)}px`;
  };
  const beginDrag = event => {
    if (event.button !== undefined && event.button !== 0) return;
    const rect = dock.getBoundingClientRect();
    dragState = { pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, left: rect.left, top: rect.top, moved: false };
    dock.classList.add("is-dragging");
    launcher.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  };
  const moveDrag = event => {
    if (!dragState || event.pointerId !== dragState.pointerId) return;
    const dx = event.clientX - dragState.startX;
    const dy = event.clientY - dragState.startY;
    if (!dragState.moved && Math.hypot(dx, dy) < 5) return;
    dragState.moved = true;
    applyDockPosition(dragState.left + dx, dragState.top + dy);
    if (!panel.hidden) positionPanelFromDock();
    event.preventDefault();
  };
  const endDrag = event => {
    if (!dragState || event.pointerId !== dragState.pointerId) return;
    suppressNextClick = dragState.moved;
    launcher.releasePointerCapture?.(event.pointerId);
    dock.classList.remove("is-dragging");
    dragState = null;
  };
  restoreDockPosition();
  const positionNpcLayout = () => {
    if (panel.hidden) return;
    if (dock.dataset.moved === "1") {
      positionPanelFromDock();
      return;
    }
    if (!shell) return;

    // 모바일/좁은 화면에서는 기존 우측 고정 배치를 유지한다.
    if (window.innerWidth <= 900) {
      panel.style.left = "";
      panel.style.right = "";
      panel.style.top = "";
      panel.style.bottom = "";
      return;
    }

    const shellRect = shell.getBoundingClientRect();
    const launcherRect = launcher.getBoundingClientRect();
    const pageGap = 3;
    const scrollbarGap = 1;
    const characterGap = 16;

    // v12: 양쪽 선을 동시에 고정한다.
    // 왼쪽  = 메인 페이지 프레임 오른쪽 + 3px
    // 오른쪽 = 브라우저 세로 스크롤바 왼쪽 - 1px
    // 폭을 고정값으로 제한하지 않고 두 경계 사이의 실제 남는 공간을 그대로 사용한다.
    const viewportRight = Math.round((document.documentElement.clientWidth || window.innerWidth) - scrollbarGap);
    const left = Math.round(shellRect.right + pageGap);
    const availableWidth = Math.max(0, viewportRight - left);

    // 데스크톱에서 공간이 정상적으로 확보되는 경우 양쪽에 정확히 맞춘다.
    // 너무 좁아지는 경우에만 최소 폭을 위해 오른쪽 고정 배치로 폴백한다.
    if (availableWidth >= 230) {
      panel.style.left = `${left}px`;
      panel.style.right = "auto";
      panel.style.width = `${availableWidth}px`;
      panel.style.maxWidth = "none";
    } else {
      panel.style.left = "auto";
      panel.style.right = "8px";
      panel.style.width = "278px";
      panel.style.maxWidth = "calc(100vw - 16px)";
    }

    // 캐릭터 머리를 가리지 않으면서 기존보다 위쪽 공간도 조금 더 활용한다.
    const desiredHeight = Math.min(410, Math.max(372, Math.round(window.innerHeight * 0.50)));
    const bottomLimit = Math.round(launcherRect.top - characterGap);
    let top = Math.round(bottomLimit - desiredHeight);
    top = Math.max(12, top);
    const actualHeight = Math.max(300, bottomLimit - top);

    panel.style.height = `${actualHeight}px`;
    panel.style.top = `${top}px`;
    panel.style.bottom = "auto";
  };

  const csrfToken = () => {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta?.content && meta.content !== "NOTPROVIDED") return meta.content;
    const found = document.cookie.split(";").map(v => v.trim()).find(v => v.startsWith("csrftoken="));
    return found ? decodeURIComponent(found.split("=").slice(1).join("=")) : "";
  };
  const scrollBottom = () => requestAnimationFrame(() => { messages.scrollTop = messages.scrollHeight; });
  const nextPose = role => {
    turnIndex += 1;
    if (role === "user") return turnIndex % 2 ? "run" : "idle";
    return poses[turnIndex % poses.length] || "wave";
  };

  const recommendationList = recommendations => {
    if (!Array.isArray(recommendations) || !recommendations.length) return null;
    const list = document.createElement("div");
    list.className = "usim-chat-rec-list";
    recommendations.slice(0, 2).forEach(item => {
      const card = document.createElement("div");
      card.className = "usim-chat-rec";
      const top = document.createElement("div");
      top.className = "usim-chat-rec-top";
      const name = document.createElement("b");
      name.textContent = item.name || "추천 시설";
      const score = document.createElement("span");
      score.textContent = item.score ? `${item.score}점` : "추천";
      top.append(name, score);
      const detail = document.createElement("small");
      const travel = item.travel_time === "확인 필요" ? "이동시간 확인 필요" : `이동 약 ${item.travel_time}분`;
      const reason = Array.isArray(item.reasons) && item.reasons.length ? ` · ${item.reasons[0]}` : "";
      detail.textContent = `${travel}${reason}`;
      card.append(top, detail);
      list.appendChild(card);
    });
    return list;
  };

  const addMessage = (role, text, recommendations = []) => {
    const row = document.createElement("div");
    row.className = `usim-chat-row ${role}`;
    const bubble = document.createElement("div");
    bubble.className = "usim-chat-bubble";
    if (role === "assistant") bubble.innerHTML = formatAssistantText(text);
    else bubble.textContent = String(text ?? "");
    const list = recommendationList(recommendations);
    if (list) bubble.appendChild(list);
    row.appendChild(bubble);
    messages.appendChild(row);
    scrollBottom();
    setPose(nextPose(role));
    if (role === "assistant" && panel.hidden) showPrompt(text, 5000);
    return row;
  };

  const addTyping = () => {
    setPose("tie");
    const row = document.createElement("div");
    row.className = "usim-chat-row assistant";
    row.dataset.typing = "1";
    const bubble = document.createElement("div");
    bubble.className = "usim-chat-bubble";
    const dots = document.createElement("span");
    dots.className = "usim-chat-typing";
    dots.innerHTML = "<i></i><i></i><i></i>";
    bubble.appendChild(dots);
    row.appendChild(bubble);
    messages.appendChild(row);
    scrollBottom();
    return row;
  };

  const greeting = () => {
    if (greeted) return;
    greeted = true;
    const nickname = document.body?.dataset.memberNickname?.trim();
    const hello = nickname
      ? `${nickname}님, 안녕! 오늘 운동이나 운동 방법이 궁금하면 편하게 물어봐.`
      : "안녕! 나는 우심이야. 오늘 운동이나 운동 방법이 궁금하면 편하게 물어봐.";
    addMessage("assistant", hello);
  };

  const openPanel = () => {
    hidePrompt();
    panel.hidden = false;
    document.body?.classList.add("usim-chat-open");
    launcher.setAttribute("aria-expanded", "true");
    requestAnimationFrame(positionNpcLayout);
    greeting();
    setTimeout(() => input.focus(), 50);
  };
  const closePanel = () => {
    panel.hidden = true;
    document.body?.classList.remove("usim-chat-open");
    launcher.setAttribute("aria-expanded", "false");
    showPrompt("필요하면 다시 말 걸어줘!", 3200);
    launcher.focus();
  };

  const send = async raw => {
    const text = String(raw || "").trim();
    if (!text || busy) return;
    if (text.length > 600) {
      addMessage("assistant", "메시지는 600자 이하로 보내줘!");
      return;
    }
    busy = true;
    input.value = "";
    input.style.height = "auto";
    sendButton.disabled = true;
    addMessage("user", text);
    const typing = addTyping();

    let profile = {};
    try { profile = app?.getProfile?.() || {}; } catch (_) { profile = {}; }
    try {
      const response = await fetch("/api/chatbot/", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify({ message: text, profile }),
      });
      const data = await response.json().catch(() => ({}));
      typing.remove();
      if (!response.ok) addMessage("assistant", data.error || "지금 연결이 조금 불안해. 잠시 후 다시 말 걸어줘!");
      else addMessage("assistant", data.reply || "답변을 만들지 못했어.", data.recommendations || []);
    } catch (_) {
      typing.remove();
      addMessage("assistant", "서버 연결을 확인해줘. 연결되면 바로 다시 얘기하자!");
    } finally {
      busy = false;
      sendButton.disabled = false;
      input.focus();
    }
  };

  launcher.addEventListener("pointerdown", beginDrag);
  launcher.addEventListener("pointermove", moveDrag);
  launcher.addEventListener("pointerup", endDrag);
  launcher.addEventListener("pointercancel", endDrag);
  launcher.addEventListener("click", () => {
    if (suppressNextClick) { suppressNextClick = false; return; }
    panel.hidden ? openPanel() : closePanel();
  });
  prompt.addEventListener("click", openPanel);
  prompt.addEventListener("keydown", event => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openPanel();
    }
  });
  promptClose?.addEventListener("click", event => {
    event.stopPropagation();
    hidePrompt();
  });
  closeButton?.addEventListener("click", closePanel);
  form.addEventListener("submit", event => { event.preventDefault(); send(input.value); });
  input.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = `${Math.min(82, input.scrollHeight)}px`;
  });
  chips.forEach(chip => chip.addEventListener("click", () => {
    send(chip.dataset.message || chip.textContent);
  }));
  clearButton?.addEventListener("click", async () => {
    if (busy) return;
    try {
      await fetch("/api/chatbot/clear/", { method:"POST", credentials:"same-origin", headers:{"X-CSRFToken":csrfToken()} });
    } catch (_) {}
    messages.replaceChildren();
    greeted = false;
    turnIndex = 0;
    greeting();
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && !panel.hidden) closePanel();
  });
  window.addEventListener("resize", () => {
    if (dock.dataset.moved === "1") {
      const rect = dock.getBoundingClientRect();
      applyDockPosition(rect.left, rect.top, true);
    }
    if (!panel.hidden) positionNpcLayout();
  });

  setPose("wave");
  window.setTimeout(() => showPrompt("오늘 운동, 나한테 물어볼래?", 5200), 650);
})();
