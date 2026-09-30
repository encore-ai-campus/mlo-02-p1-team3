(() => {
  const app = window.USIMUNKKA;
  if (!app) return;

  const isRoomVisitor = document.body?.dataset.roomVisitor === "1";
  const roomOwnerId = document.body?.dataset.roomOwnerId?.trim() || document.body?.dataset.memberId?.trim() || "";
  const memberNickname = document.body?.dataset.roomOwnerNickname?.trim() || document.body?.dataset.memberNickname?.trim() || "";
  const memberAddress = document.body?.dataset.roomOwnerAddress?.trim() || document.body?.dataset.memberAddress?.trim() || "";
  const memberId = document.body?.dataset.memberId?.trim() || "";
  const isGuest = document.body?.dataset.isGuest === "1";
  const isMember = Boolean(memberId) && !isRoomVisitor;
  const canEdit = isMember && !isGuest;
  const csrfToken = document.querySelector("meta[name='csrf-token']")?.content || "";
  const serverLocationLoaded = document.body?.dataset.locationLoaded === "1";
  const pageParams = new URLSearchParams(window.location.search);
  const pageLatitude = Number(pageParams.get("latitude"));
  const pageLongitude = Number(pageParams.get("longitude"));
  if (Number.isFinite(pageLatitude) && Number.isFinite(pageLongitude) && !(pageLatitude === 0 && pageLongitude === 0)) {
    window.__usimunkkaCurrentLocation = { latitude: pageLatitude, longitude: pageLongitude };
  }
  let initialRecommendations = [];
  try {
    initialRecommendations = JSON.parse(document.getElementById("initialRecommendations")?.textContent || "[]");
  } catch (_) {
    initialRecommendations = [];
  }
  const profile = { ...app.getProfile(), ...(memberAddress ? { address: memberAddress } : {}) };
  const $ = selector => document.querySelector(selector);
  const set = (selector, value) => {
    const el = $(selector);
    if (el) el.textContent = value;
  };
  const sportLabel = sport => app.SPORT_META[sport]?.label || sport;
  const transportLabel = app.TRANSPORT_META[profile.transport] || profile.transport;

  const accountStorageKey = roomOwnerId || "guest";
  const ROOM_STATE_KEY = `usimunkka.v1.room.state.${accountStorageKey}.v93`;
  const LAYOUT_KEY = `usimunkka.v1.room.layout.${accountStorageKey}.v93`;
  const defaultVisible = {
    window: true,
    poster: true,
    bed: true,
    shelf: true,
    desk: true,
    rug: true,
    plant: true,
    lamp: true,
    character: true,
    bottle: false,
    towel: false,
    dumbbell: false,
    gymbag: false,
    shoes: false,
    medal: false,
    specialShelf: false,
    specialTurntable: false,
    specialAmp: false,
    specialSofa: false,
    specialRug: false,
    specialLamp: false,
    finalLamp: true,
    finalAmp: true,
    finalBookshelf: true,
    finalCabinet: true,
    finalScroll: true,
    finalSideTable: true,
    finalSofa: true,
    finalRecord: true,
    finalRug: true,
  };
  const defaultState = { tone: "cream", characterSkin: "default", visible: { ...defaultVisible } };
  const ROOM_REWARDS = [];
  const MAX_TOTAL_CALORIES = 600000;
  const MAX_ROOM_LEVEL = 100;
  const BASE_LEVEL_EXP = 100;
  const LEVEL_EXPONENT = 1.6;
  const rawLevelTotal = Array.from({ length: MAX_ROOM_LEVEL - 1 }, (_, index) => BASE_LEVEL_EXP * Math.pow(index + 1, LEVEL_EXPONENT)).reduce((sum, value) => sum + value, 0);
  const levelCount = MAX_ROOM_LEVEL - 1;
  const curveScale = (MAX_TOTAL_CALORIES - BASE_LEVEL_EXP * levelCount) / (rawLevelTotal - BASE_LEVEL_EXP * levelCount);
  const levelCosts = Array.from({ length: MAX_ROOM_LEVEL - 1 }, (_, index) => Math.max(index === 0 ? BASE_LEVEL_EXP : 1, Math.round(BASE_LEVEL_EXP + (BASE_LEVEL_EXP * Math.pow(index + 1, LEVEL_EXPONENT) - BASE_LEVEL_EXP) * curveScale)));
  levelCosts[levelCosts.length - 1] += MAX_TOTAL_CALORIES - levelCosts.reduce((sum, value) => sum + value, 0);
  const levelStarts = [0];
  levelCosts.forEach(cost => levelStarts.push(levelStarts.at(-1) + cost));
  const ROOM_LEVEL_TITLES = ["STARTER", "MOVER", "PACE MAKER", "ATHLETE", "ROOM MAKER", "MOVE MASTER"];
  const SPECIAL_ITEMS = [];
  const CHARACTER_SKINS = {
    default: { level: 1, src: null, label: "기본 캐릭터" },
    rockMale: { level: 20, src: "/static/assets/images/room/special/rock-male.png", label: "ROCK MALE" },
    rockFemale: { level: 20, src: "/static/assets/images/room/special/rock-female.png", label: "ROCK FEMALE" },
    highendMale: { level: 50, src: "/static/assets/images/room/special/highend-male.png", label: "HIGHEND MALE" },
    highendFemale: { level: 50, src: "/static/assets/images/room/special/highend-female.png", label: "HIGHEND FEMALE" },
    hanbokFemale: { level: 5, src: "/static/assets/images/room/special/hanbok-female.png", label: "HANBOK FEMALE" },
    hanbokMale: { level: 5, src: "/static/assets/images/room/special/hanbok-male.png", label: "HANBOK MALE" },
    hanbokFemale2: { level: 5, src: "/static/assets/images/room/special/hanbok-female-2.png", label: "HANBOK FEMALE 2" },
    hanbokMale2: { level: 5, src: "/static/assets/images/room/special/hanbok-male-2.png", label: "HANBOK MALE 2" },
    hanbokRedFemale: { level: 1, src: "/static/assets/images/room/special/hanbok-red-female.png", label: "꽃무늬 한복 여성" },
    hanbokOrangeMale: { level: 1, src: "/static/assets/images/room/special/hanbok-orange-male.png", label: "주황 한복 남성" },
    hanbokBlackMale: { level: 1, src: "/static/assets/images/room/special/hanbok-black-male.png", label: "검정 한복 남성" },
    hanbokBlackFemale: { level: 1, src: "/static/assets/images/room/special/hanbok-black-female.png", label: "검정 한복 여성" },
    hanbokPinkFemale: { level: 1, src: "/static/assets/images/room/special/hanbok-pink-female.png", label: "분홍 한복 여성" },
  };

  const getRoomLevelInfo = rawTotal => {
    const total = Math.max(0, Math.floor(Number(rawTotal) || 0));
    const levelTotal = Math.min(MAX_TOTAL_CALORIES, total);
    let level = 1;
    while (level < MAX_ROOM_LEVEL && levelTotal >= levelStarts[level]) level += 1;
    if (level >= MAX_ROOM_LEVEL) return { total, level: MAX_ROOM_LEVEL, exp: total - MAX_TOTAL_CALORIES, nextExp: 0, percent: 100, remaining: 0, title: ROOM_LEVEL_TITLES.at(-1) };
    const nextExp = levelCosts[level - 1];
    const exp = total - levelStarts[level - 1];
    const percent = Math.max(0, Math.min(100, (exp / nextExp) * 100));
    const remaining = nextExp - exp;
    const title = ROOM_LEVEL_TITLES[Math.min(level - 1, ROOM_LEVEL_TITLES.length - 1)];
    return { total, level, exp, nextExp, percent, remaining, title };
  };

  const safeJson = (key, fallback) => {
    try {
      const parsed = JSON.parse(localStorage.getItem(key) || "null");
      return parsed && typeof parsed === "object" ? parsed : fallback;
    } catch (_) {
      return fallback;
    }
  };

  const readRoomState = () => {
    const stored = safeJson(ROOM_STATE_KEY, {});
    const tone = ["cream", "sage", "blue"].includes(stored.tone) ? stored.tone : defaultState.tone;
    return {
      tone,
      characterSkin: Object.prototype.hasOwnProperty.call(CHARACTER_SKINS, stored.characterSkin) ? stored.characterSkin : defaultState.characterSkin,
      visible: { ...defaultVisible, ...(stored.visible || {}) },
    };
  };

  let savedState = readRoomState();
  let draftState = JSON.parse(JSON.stringify(savedState));

  set("#homeNickname", memberNickname || profile.nickname);
  set("#homeRegion", memberAddress || `${profile.province} ${profile.district}`);
  set("#homePreference", `${profile.preferred_sports.map(sportLabel).join(" · ")} · ${transportLabel} ${profile.max_travel_minutes}분 기준`);

  let serverProgress = isMember
    ? { total_calories: 0, entries: [] }
    : (isRoomVisitor ? { total_calories: Number(document.body?.dataset.roomOwnerCalories || 0), entries: [] } : null);
  const getWorkoutProgress = () => serverProgress || app.getWorkoutProgress?.() || { total_calories: 0, entries: [] };
  const isUnlocked = (key, total = getWorkoutProgress().total_calories) => {
    const reward = ROOM_REWARDS.find(item => item.key === key);
    const special = SPECIAL_ITEMS.find(item => item.key === key);
    return (!reward || total >= reward.calories) && (!special || getRoomLevelInfo(total).level >= special.level);
  };
  const isSkinUnlocked = (key, total = getWorkoutProgress().total_calories) => getRoomLevelInfo(total).level >= (CHARACTER_SKINS[key]?.level || 1);
  const applyCharacterSkin = skinKey => {
    const image = $("#roomCharacterImage");
    if (!image) return;
    const skin = CHARACTER_SKINS[skinKey] || CHARACTER_SKINS.default;
    if (skin.src && isSkinUnlocked(skinKey)) {
      image.src = skin.src;
    } else {
      const gender = app.getProfile?.().avatar_gender || profile.avatar_gender || "male";
      image.src = gender === "female" ? image.dataset.femaleSrc : image.dataset.maleSrc;
    }
    image.dataset.skin = skin.src && isSkinUnlocked(skinKey) ? skinKey : "default";
  };

  const applyRoomState = state => {
    const room = $("#sportsRoom");
    if (!room) return;
    room.dataset.tone = state.tone;
    const skinKey = isSkinUnlocked(state.characterSkin) ? state.characterSkin : "default";
    applyCharacterSkin(skinKey);
    room.dataset.characterSkin = skinKey;
    document.querySelectorAll("[data-room-item]").forEach(item => {
      const key = item.dataset.roomItem;
      const unlocked = isUnlocked(key);
      // 캐릭터는 방의 기본 구성 요소이므로 예전 계정 상태에 false가
      // 저장되어 있어도 항상 표시한다. (구버전 커스터마이저 복구 대응)
      const visible = key === "character" ? true : unlocked && state.visible[key] !== false;
      item.classList.toggle("is-room-hidden", !visible);
      item.classList.toggle("is-room-locked", !unlocked);
    });
  };

  const syncCustomizer = () => {
    document.querySelectorAll("[data-tone]").forEach(button => {
      button.classList.toggle("is-selected", button.dataset.tone === draftState.tone);
    });
    const total = getWorkoutProgress().total_calories;
    document.querySelectorAll("[data-toggle-item]").forEach(button => {
      const key = button.dataset.toggleItem;
      const unlocked = isUnlocked(key, total);
      button.classList.toggle("is-locked", !unlocked);
      button.classList.toggle("is-selected", unlocked && draftState.visible[key] !== false);
      button.setAttribute("aria-disabled", String(!unlocked));
      const status = button.querySelector("small");
      if (status && button.dataset.unlockCalories) status.textContent = unlocked ? "UNLOCKED" : "LOCKED";
    });
    document.querySelectorAll("[data-special-item]").forEach(button => {
      const key = button.dataset.specialItem;
      const unlocked = isUnlocked(key, total);
      button.classList.toggle("is-locked", !unlocked);
      button.classList.toggle("is-selected", unlocked && draftState.visible[key] !== false);
      button.setAttribute("aria-disabled", String(!unlocked));
      const status = button.querySelector("small");
      if (status) status.textContent = unlocked ? (draftState.visible[key] !== false ? "ON" : "OFF") : `LV. ${button.dataset.unlockLevel} LOCKED`;
    });
    document.querySelectorAll("[data-character-skin]").forEach(button => {
      const key = button.dataset.characterSkin;
      const unlocked = isSkinUnlocked(key, total);
      button.classList.toggle("is-locked", !unlocked);
      button.classList.toggle("is-selected", unlocked && draftState.characterSkin === key);
      button.setAttribute("aria-disabled", String(!unlocked));
      const status = button.querySelector("small");
      if (status) status.textContent = unlocked ? (draftState.characterSkin === key ? "EQUIPPED" : `LV. ${button.dataset.unlockLevel}`) : `LV. ${button.dataset.unlockLevel} LOCKED`;
    });
    applyRoomState(draftState);
  };

  const openCustomizer = () => {
    if (!canEdit) return;
    draftState = JSON.parse(JSON.stringify(savedState));
    syncCustomizer();
    const backdrop = $("#customizerBackdrop");
    if (backdrop) backdrop.hidden = false;
    document.body.style.overflow = "hidden";
  };

  const closeCustomizer = restore => {
    if (restore) applyRoomState(savedState);
    const backdrop = $("#customizerBackdrop");
    if (backdrop) backdrop.hidden = true;
    document.body.style.overflow = "";
  };

  $("#openCustomizer")?.addEventListener("click", openCustomizer);
  $("#closeCustomizer")?.addEventListener("click", () => closeCustomizer(true));
  $("#customizerBackdrop")?.addEventListener("click", event => {
    if (event.target === event.currentTarget) closeCustomizer(true);
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && !$("#customizerBackdrop")?.hidden) closeCustomizer(true);
  });

  document.querySelectorAll("[data-tone]").forEach(button => {
    button.addEventListener("click", () => {
      draftState.tone = button.dataset.tone;
      syncCustomizer();
    });
  });

  document.querySelectorAll("[data-toggle-item]").forEach(button => {
    button.addEventListener("click", () => {
      const key = button.dataset.toggleItem;
      if (!isUnlocked(key)) {
        const need = Number(button.dataset.unlockCalories || 0);
        set("#customizerSaveMessage", `${need.toLocaleString("ko-KR")} kcal를 채우면 열리는 소품이에요.`);
        return;
      }
      draftState.visible[key] = !(draftState.visible[key] !== false);
      syncCustomizer();
    });
  });

  document.querySelectorAll("[data-special-item]").forEach(button => {
    button.addEventListener("click", () => {
      const key = button.dataset.specialItem;
      if (!isUnlocked(key)) {
        set("#customizerSaveMessage", `ROOM LV.${button.dataset.unlockLevel}에서 열리는 특별 소품이에요.`);
        return;
      }
      draftState.visible[key] = !(draftState.visible[key] !== false);
      syncCustomizer();
    });
  });

  document.querySelectorAll("[data-character-skin]").forEach(button => {
    button.addEventListener("click", () => {
      const key = button.dataset.characterSkin;
      if (!isSkinUnlocked(key)) {
        set("#customizerSaveMessage", `ROOM LV.${button.dataset.unlockLevel}에서 열리는 캐릭터예요.`);
        return;
      }
      draftState.characterSkin = key;
      syncCustomizer();
    });
  });

  $("#saveCustomizer")?.addEventListener("click", () => {
    if (!canEdit) return;
    savedState = JSON.parse(JSON.stringify(draftState));
    localStorage.setItem(ROOM_STATE_KEY, JSON.stringify(savedState));
    applyRoomState(savedState);
    persistRoomState();
    set("#customizerSaveMessage", "저장했어요. 내 방에 바로 반영됐어요.");
    window.setTimeout(() => closeCustomizer(false), 450);
  });

  const roomScene = $("#roomScene");
  const draggableItems = [...document.querySelectorAll("[data-room-item]")];
  let activeDrag = null;

  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
  const getLimits = item => ({
    minX: Number(item.dataset.minX || 5),
    maxX: Number(item.dataset.maxX || 95),
    minY: Number(item.dataset.minY || 10),
    maxY: Number(item.dataset.maxY || 91),
  });

  const setItemPosition = (item, x, y, save = false) => {
    const limits = getLimits(item);
    const nx = clamp(Number(x), limits.minX, limits.maxX);
    const ny = clamp(Number(y), limits.minY, limits.maxY);
    item.style.left = `${nx}%`;
    item.style.top = `${ny}%`;
    item.dataset.x = String(nx);
    item.dataset.y = String(ny);
    if (save) saveLayout();
  };

  const saveLayout = () => {
    if (!canEdit) return;
    const state = {};
    draggableItems.forEach(item => {
      state[item.dataset.roomItem] = {
        x: Number(item.dataset.x || item.dataset.defaultX || 50),
        y: Number(item.dataset.y || item.dataset.defaultY || 50),
      };
    });
    localStorage.setItem(LAYOUT_KEY, JSON.stringify(state));
    persistRoomState();
  };

  const persistRoomState = async () => {
    if (!canEdit) return;
    try {
      await fetch("/api/room-state/", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken, Accept: "application/json" },
        body: JSON.stringify({ state: savedState, layout: safeJson(LAYOUT_KEY, {}) }),
      });
    } catch (_) {}
  };

  const loadServerRoomState = async () => {
    const url = isRoomVisitor ? `/api/room-state/${encodeURIComponent(roomOwnerId)}/` : (isMember ? "/api/room-state/" : "");
    if (!url) return;
    try {
      const response = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("방 상태 조회 실패");
      const payload = await response.json();
      const hasServerState = payload.state && Object.keys(payload.state).length;
      const hasServerLayout = payload.layout && Object.keys(payload.layout).length;
      if (hasServerState) {
        savedState = { tone: payload.state.tone || defaultState.tone, characterSkin: Object.prototype.hasOwnProperty.call(CHARACTER_SKINS, payload.state.characterSkin) ? payload.state.characterSkin : defaultState.characterSkin, visible: { ...defaultVisible, ...(payload.state.visible || {}) } };
        draftState = JSON.parse(JSON.stringify(savedState));
      }
      if (hasServerLayout) localStorage.setItem(LAYOUT_KEY, JSON.stringify(payload.layout));
      if (!isRoomVisitor && (!hasServerState || !hasServerLayout)) persistRoomState();
    } catch (_) {}
  };

  const restoreLayout = () => {
    const savedLayout = safeJson(LAYOUT_KEY, {});
    draggableItems.forEach(item => {
      const key = item.dataset.roomItem;
      const saved = savedLayout[key];
      const x = saved?.x ?? Number(item.dataset.defaultX || 50);
      const y = saved?.y ?? Number(item.dataset.defaultY || 50);
      setItemPosition(item, x, y, false);
    });
  };

  const pointerPosition = event => {
    const rect = roomScene.getBoundingClientRect();
    return {
      x: ((event.clientX - rect.left) / rect.width) * 100,
      y: ((event.clientY - rect.top) / rect.height) * 100,
    };
  };

  draggableItems.forEach(item => {
    item.addEventListener("pointerdown", event => {
      if (!canEdit) return;
      if (item.classList.contains("is-room-hidden")) return;
      if (event.button !== undefined && event.button !== 0) return;
      const sceneRect = roomScene.getBoundingClientRect();
      const itemRect = item.getBoundingClientRect();
      activeDrag = {
        item,
        offsetX: ((event.clientX - (itemRect.left + itemRect.width / 2)) / sceneRect.width) * 100,
        offsetY: ((event.clientY - (itemRect.top + itemRect.height / 2)) / sceneRect.height) * 100,
      };
      item.classList.add("is-dragging");
      item.setPointerCapture?.(event.pointerId);
      event.preventDefault();
    });

    item.addEventListener("pointermove", event => {
      if (activeDrag?.item !== item) return;
      const pos = pointerPosition(event);
      setItemPosition(item, pos.x - activeDrag.offsetX, pos.y - activeDrag.offsetY, false);
    });

    const endDrag = event => {
      if (activeDrag?.item !== item) return;
      item.classList.remove("is-dragging");
      item.releasePointerCapture?.(event.pointerId);
      activeDrag = null;
      saveLayout();
    };
    item.addEventListener("pointerup", endDrag);
    item.addEventListener("pointercancel", endDrag);

    item.addEventListener("keydown", event => {
      if (!canEdit) return;
      if (item.classList.contains("is-room-hidden")) return;
      const keys = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"];
      if (!keys.includes(event.key)) return;
      event.preventDefault();
      const step = event.shiftKey ? 3 : 1;
      let x = Number(item.dataset.x || item.dataset.defaultX || 50);
      let y = Number(item.dataset.y || item.dataset.defaultY || 50);
      if (event.key === "ArrowLeft") x -= step;
      if (event.key === "ArrowRight") x += step;
      if (event.key === "ArrowUp") y -= step;
      if (event.key === "ArrowDown") y += step;
      setItemPosition(item, x, y, true);
    });
  });

  $("#resetRoomLayout")?.addEventListener("click", () => {
    if (!canEdit) return;
    draggableItems.forEach(item => {
      setItemPosition(item, Number(item.dataset.defaultX || 50), Number(item.dataset.defaultY || 50), false);
    });
    localStorage.removeItem(LAYOUT_KEY);
  });

  const renderWorkoutProgress = (flashMessage = "") => {
    const progress = getWorkoutProgress();
    const total = Math.max(0, Math.floor(Number(progress.total_calories) || 0));
    const levelInfo = getRoomLevelInfo(total);
    const nextReward = ROOM_REWARDS.find(item => total < item.calories);

    set("#roomTotalCalories", `${total.toLocaleString("ko-KR")} kcal TOTAL`);
    set("#roomLevelBadge", `LV. ${levelInfo.level}`);
    set("#roomLevelTitle", levelInfo.title);
    set("#roomLevelExp", levelInfo.level >= MAX_ROOM_LEVEL
      ? `MAX LEVEL · +${levelInfo.exp.toLocaleString("ko-KR")} MOVE EXP`
      : `${levelInfo.exp.toLocaleString("ko-KR")} / ${levelInfo.nextExp.toLocaleString("ko-KR")} MOVE EXP`);
    set("#roomNextLevel", levelInfo.level >= MAX_ROOM_LEVEL
      ? "최대 레벨에 도달했어요"
      : `다음 레벨까지 ${levelInfo.remaining.toLocaleString("ko-KR")} kcal`);
    set("#roomLevelPercent", `${Math.floor(levelInfo.percent)}%`);

    const bar = $("#roomProgressBar");
    if (bar) bar.style.width = `${levelInfo.percent}%`;

    if (flashMessage) {
      set("#roomUnlockMessage", flashMessage);
    } else if (nextReward) {
      set("#roomUnlockMessage", `다음 소품 · ${nextReward.label} — ${Math.max(0, nextReward.calories - total).toLocaleString("ko-KR")} kcal 남았어요.`);
    } else {
      set("#roomUnlockMessage", `새 방 소품은 모두 자유롭게 배치할 수 있어요 · ROOM LV.${levelInfo.level} 성장 중!`);
    }

    syncCustomizer();
  };

  $("#workoutLogForm")?.addEventListener("submit", async event => {
    event.preventDefault();
    if (!canEdit) return;
    const input = $("#workoutCaloriesInput");
    const numericValue = Number(input?.value || 0);
    const amount = Math.round(numericValue);

    if (!Number.isFinite(numericValue) || !Number.isSafeInteger(amount) || amount <= 0) {
      set("#roomUnlockMessage", "1 kcal 이상의 숫자를 입력해주세요. 상한은 없어요.");
      input?.focus();
      return;
    }

    const before = Math.max(0, Math.floor(Number(getWorkoutProgress().total_calories) || 0));
    const beforeLevel = getRoomLevelInfo(before).level;
    let progress;
    if (canEdit) {
      try {
        const response = await fetch("/workout-calories-data/", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken, Accept: "application/json" },
          body: JSON.stringify({ calories: amount }),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "운동량 저장에 실패했습니다.");
        serverProgress = payload;
        progress = payload;
      } catch (error) {
        set("#roomUnlockMessage", error.message);
        return;
      }
    } else {
      progress = app.addWorkoutCalories?.(amount) || { total_calories: before + amount };
    }
    const after = Math.max(0, Math.floor(Number(progress.total_calories) || before + amount));
    const afterLevel = getRoomLevelInfo(after).level;
    const newlyUnlocked = ROOM_REWARDS.filter(item => before < item.calories && after >= item.calories);
    const newlySpecialUnlocked = SPECIAL_ITEMS.filter(item => beforeLevel < item.level && afterLevel >= item.level);

    if (newlyUnlocked.length) {
      newlyUnlocked.forEach(item => { savedState.visible[item.key] = true; });
      localStorage.setItem(ROOM_STATE_KEY, JSON.stringify(savedState));
      draftState = JSON.parse(JSON.stringify(savedState));
      applyRoomState(savedState);
    }

    const messages = [`${amount.toLocaleString("ko-KR")} kcal 기록 완료`];
    if (newlyUnlocked.length) messages.push(`${newlyUnlocked.map(item => item.label).join(" · ")} 해금`);
    if (newlySpecialUnlocked.length) messages.push(`특별 보상 ${newlySpecialUnlocked.map(item => item.label).join(" · ")} 해금`);
    if (afterLevel > beforeLevel) {
      messages.push(afterLevel - beforeLevel > 1
        ? `ROOM LV.${beforeLevel} → LV.${afterLevel} 점프!`
        : `ROOM LV.${afterLevel} LEVEL UP!`);
    } else if (!newlyUnlocked.length) {
      messages.push(`LV.${afterLevel} EXP +${amount.toLocaleString("ko-KR")}`);
    }

    renderWorkoutProgress(messages.join(" · "));

    const card = $("#roomProgressCard");
    if (afterLevel > beforeLevel && card) {
      card.classList.remove("is-level-up");
      void card.offsetWidth;
      card.classList.add("is-level-up");
      window.setTimeout(() => card.classList.remove("is-level-up"), 900);
    }

    if (input) input.value = "";
  });

  $("#resetProgressButton")?.addEventListener("click", async () => {
    if (!canEdit) return;
    if (!window.confirm("누적 칼로리와 운동 기록을 모두 지우고 LV.1로 초기화할까요?")) return;
    try {
      const response = await fetch("/api/workout-calories/reset/", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken, Accept: "application/json" },
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "레벨 초기화에 실패했습니다.");
      serverProgress = payload;
      savedState.characterSkin = "default";
      draftState.characterSkin = "default";
      localStorage.removeItem(ROOM_STATE_KEY);
      renderWorkoutProgress("운동량을 초기화했어요 · LV.1부터 다시 시작합니다.");
      set("#workoutCaloriesInput", "");
    } catch (error) {
      set("#roomUnlockMessage", error.message);
    }
  });

  $("#undoWorkoutButton")?.addEventListener("click", async () => {
    if (!canEdit) return;
    if (!window.confirm("가장 최근 운동 기록을 되돌릴까요? 해당 칼로리만 차감됩니다.")) return;
    try {
      const response = await fetch("/api/workout-calories/undo/", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken, Accept: "application/json" },
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "최근 기록을 되돌리지 못했습니다.");
      serverProgress = payload;
      renderWorkoutProgress("최근 운동 기록을 되돌렸어요.");
    } catch (error) {
      set("#roomUnlockMessage", error.message);
    }
  });

  const sportBadge = sport => ({ running: "RUN", cycling: "RIDE", crossfit: "CF", fitness: "GYM" }[sport] || "MOVE");
  const scoreNumber = row => Number.isFinite(Number(row?.score)) ? Number(row.score) : -1;
  const recommendationOrder = rows => [...(rows || [])].sort((a, b) => (
    scoreNumber(b) - scoreNumber(a)
    || (Number(a.distance_km ?? Number.POSITIVE_INFINITY) - Number(b.distance_km ?? Number.POSITIVE_INFINITY))
  ));
  let locationPromise;
  const requestCurrentLocation = () => {
    if (locationPromise) return locationPromise;
    locationPromise = new Promise(resolve => {
      if (!navigator.geolocation) return resolve(null);
      navigator.geolocation.getCurrentPosition(
        position => resolve({ latitude: position.coords.latitude, longitude: position.coords.longitude }),
        () => resolve(null),
        { enableHighAccuracy: false, timeout: 3000, maximumAge: 300000 },
      );
    });
    return locationPromise;
  };

  const renderQuick = async () => {
    const requestedMinutes = pageParams.get("available_minutes");
    const minutes = Number(requestedMinutes || $("#quickMinutes")?.value || 60);
    const minutesInput = $("#quickMinutes");
    if (minutesInput && ["30", "60", "90", "120"].includes(requestedMinutes || "")) {
      minutesInput.value = requestedMinutes;
    }
    // 위치 확인을 기다리지 않고 로그인 지역 추천을 먼저 표시한다.
    // GPS가 확인되면 아래 백그라운드 요청이 현재 위치 기준 결과로 교체한다.
    const currentLocation = null;
    const region = memberAddress || `${profile.province || ""} ${profile.district || ""}`.trim();
    const parts = region.split(/\s+/).filter(Boolean);
    const aliases = { 수원: ["경기도", "수원시"], 수원시: ["경기도", "수원시"] };
    const normalized = aliases[parts.join(" ")] || aliases[parts.at(-1)] || [parts[0], parts.at(-1)];
    const selectedSport = profile.preferred_sports?.[0] || "fitness";
    let result;
    try {
      const params = new URLSearchParams({
        province: normalized[0] || "",
        district: normalized[1] || "",
        sports: selectedSport,
        available_minutes: String(minutes),
        max_travel_minutes: String(profile.max_travel_minutes || 20),
        transport: profile.transport || "walk",
      });
      if (currentLocation) {
        params.set("latitude", String(currentLocation.latitude));
        params.set("longitude", String(currentLocation.longitude));
      }
      const response = await fetch(`/nearby-facilities-data/?${params}`, { credentials: "same-origin", headers: { Accept: "application/json" } });
      const data = await response.json();
      if (!response.ok || !data.recommendations?.length) throw new Error("지역·운동 조건에 맞는 시설 없음");
      const item = recommendationOrder(data.recommendations)[0];
      result = {
        ...item,
        sport: item.sport || selectedSport,
        name: item.name || item.facility_name,
        travel_minutes: item.travel_time,
        indoor: item.indoor,
        reasons: item.reasons || [],
      };
    } catch (_) {
      // 다른 지역의 기본 샘플을 보여주면 사용자에게 잘못된 추천이 되므로,
      // API 실패 시에는 지역이 다른 가짜 시설을 대신 표시하지 않는다.
      set("#spotlightIcon", selectedSport === "fitness" ? "GYM" : "MOVE");
      set("#spotlightSport", sportLabel(selectedSport));
      set("#spotlightTitle", `${region} 추천을 불러오지 못했어요`);
      set("#spotlightMeta", `${sportLabel(selectedSport)} · ${profile.transport || "도보"} · 지역 일치 시설만 표시`);
      const tags = $("#spotlightTags");
      if (tags) tags.innerHTML = "<span>다시 추천을 눌러 재시도하세요</span>";
      return;
    }
    set("#spotlightIcon", sportBadge(result.sport));
    set("#spotlightSport", sportLabel(result.sport));
    set("#spotlightTitle", result.name);
    const distanceLabel = result.distance_km != null ? `${result.distance_km}km · ` : "";
    set("#spotlightMeta", `${sportLabel(result.sport)} · ${distanceLabel}${transportLabel} ${result.travel_minutes}분 · ${result.indoor ? "실내" : "야외"}`);
    const tags = $("#spotlightTags");
    if (tags) {
      const visibleReasons = result.reasons.filter(reason => reason !== "시설 기본정보 확인").slice(0, 3);
      tags.innerHTML = visibleReasons.map(reason => `<span>${reason}</span>`).join("");
    }

  };

  const renderTalks = rows => {
    const list = $("#homeTalkList");
    if (!list) return;
    const talks = Array.isArray(rows) ? rows : app.getTalks().slice(0, 3);
    list.innerHTML = talks.slice(0, 3).map(row => `
      <div class="talk-row"><b>${row.author}</b><span>${row.text}</span><time>${row.time}</time></div>
    `).join("");
  };

  const loadTalks = async () => {
    if (!isMember) {
      renderTalks();
      return;
    }
    try {
      const response = await fetch("/api/friend-notes/", { credentials: "same-origin", headers: { Accept: "application/json" } });
      const payload = await response.json();
      if (!response.ok) throw new Error("한마디 조회 실패");
      renderTalks(payload.notes);
    } catch (_) {
      renderTalks();
    }
  };

  const reloadRecommendation = async () => {
    const minutes = Number($("#quickMinutes")?.value || 60);
    const params = new URLSearchParams({
      available_minutes: String(minutes),
      max_travel_minutes: String(profile.max_travel_minutes || 20),
      refresh: String(Date.now()),
    });
    window.location.href = `${document.body.dataset.homeUrl || "/main/"}?${params}`;
  };

  $("#quickRecommendButton")?.addEventListener("click", reloadRecommendation);
  $("#quickMinutes")?.addEventListener("change", reloadRecommendation);
  $("#homeTalkForm")?.addEventListener("submit", event => {
    event.preventDefault();
    if (!canEdit) return;
    const input = $("#homeTalkInput");
    const text = input.value.trim();
    if (!text) return;
    if (canEdit) {
      fetch("/api/friend-notes/create/", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken, Accept: "application/json" },
        body: JSON.stringify({ text }),
      }).then(response => response.ok ? response.json() : Promise.reject(new Error("한마디 저장 실패")))
        .then(() => { input.value = ""; loadTalks(); })
        .catch(() => {});
      return;
    }
    app.addTalk(text, memberNickname || profile.nickname);
    input.value = "";
    renderTalks();
  });

  const bootHome = async () => {
    await loadServerRoomState();
    applyRoomState(savedState);
    restoreLayout();
    renderWorkoutProgress();
    loadTalks();
    if (isMember) {
      fetch("/account-state-data/", { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(response => response.ok ? response.json() : Promise.reject(new Error("계정 상태 조회 실패")))
        .then(payload => {
          serverProgress = payload;
          renderWorkoutProgress();
        })
        .catch(() => {});
    }
    renderQuick();
  };
  bootHome();
})();
