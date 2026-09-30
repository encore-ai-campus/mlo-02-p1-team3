(() => {
  const app = window.USIMUNKKA;
  const profile = app.getProfile();
  const $ = selector => document.querySelector(selector);
  const escapeHtml = value => String(value ?? "").replace(/[&<>'"]/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[ch]));

  const parseMemberAddress = address => {
    const parts = String(address || "").trim().split(/\s+/).filter(Boolean);
    if (parts.length < 2) return {};
    const provinceIndex = parts.findIndex(part => /(특별시|광역시|자치시|자치도|도)$/.test(part));
    const districtIndex = provinceIndex >= 0
      ? parts.findIndex((part, index) => index > provinceIndex && /(시|군|구)$/.test(part))
      : -1;
    if (provinceIndex < 0 || districtIndex < 0) return {};
    return { province: parts[provinceIndex], district: parts[districtIndex] };
  };

  const memberAddress = document.body?.dataset.memberAddress || "";
  const memberRegion = parseMemberAddress(memberAddress);

  $("#provinceInput").value = memberRegion.province || profile.province || "";
  $("#districtInput").value = memberRegion.district || profile.district || "";
  $("#transportSelect").value = profile.transport || "walk";
  $("#travelMinutesSelect").value = String(profile.max_travel_minutes || 20);
  const preferred = profile.preferred_sports?.[0] || "running";
  const initialSport = document.querySelector(`input[name='sport'][value='${preferred}']`) || document.querySelector("input[name='sport']");
  if (initialSport) initialSport.checked = true;

  let resultRows = [];
  let resultPage = 0;
  let resultNotice = "";
  const pageSize = 3;
  let currentLocation = null;
  let locationMode = "region";
  let selectedRecommendationId = null;

  const locationButton = $("#currentLocationButton");
  const locationStatus = $("#currentLocationStatus");
  const manualRegionPanel = $("#manualRegionPanel");
  const currentLocationPanel = $("#currentLocationPanel");
  const manualRegionHint = $("#manualRegionHint");
  const manualRegionModeButton = $("#manualRegionModeButton");
  const currentLocationModeButton = $("#currentLocationModeButton");

  const setLocationMode = mode => {
    locationMode = mode;
    const isCurrent = mode === "current";
    manualRegionPanel?.classList.toggle("is-hidden", isCurrent);
    manualRegionHint?.classList.toggle("is-hidden", isCurrent);
    currentLocationPanel?.classList.toggle("is-hidden", !isCurrent);
    manualRegionModeButton?.classList.toggle("is-active", !isCurrent);
    currentLocationModeButton?.classList.toggle("is-active", isCurrent);
    manualRegionModeButton?.setAttribute("aria-pressed", String(!isCurrent));
    currentLocationModeButton?.setAttribute("aria-pressed", String(isCurrent));
    if (!isCurrent) {
      currentLocation = null;
      setLocationStatus("현재 위치를 확인하면 주변 시설을 검색할 수 있습니다.");
    }
  };

  manualRegionModeButton?.addEventListener("click", () => setLocationMode("region"));
  currentLocationModeButton?.addEventListener("click", () => setLocationMode("current"));

  const setLocationStatus = (message, state = "") => {
    if (!locationStatus) return;
    locationStatus.textContent = message;
    locationStatus.classList.toggle("is-success", state === "success");
    locationStatus.classList.toggle("is-error", state === "error");
  };

  const getCurrentLocation = () => new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error("이 브라우저에서는 위치 정보를 사용할 수 없습니다."));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      position => resolve({ latitude: position.coords.latitude, longitude: position.coords.longitude }),
      error => {
        const messages = {
          1: "위치 권한이 거부되었습니다. 브라우저 주소창의 위치 권한을 허용해주세요.",
          2: "현재 위치를 확인할 수 없습니다. 잠시 후 다시 시도해주세요.",
          3: "위치 확인 시간이 초과되었습니다. 다시 시도해주세요.",
        };
        reject(new Error(messages[error.code] || "위치 정보를 확인하지 못했습니다."));
      },
      { enableHighAccuracy: false, timeout: 5000, maximumAge: 120000 },
    );
  });

  locationButton?.addEventListener("click", async () => {
    locationButton.disabled = true;
    locationButton.querySelector("span").textContent = "…";
    setLocationStatus("현재 위치를 확인하는 중입니다…");
    try {
      currentLocation = await getCurrentLocation();
      setLocationStatus("현재 위치를 확인했습니다. 운동을 선택한 뒤 추천 버튼을 눌러주세요.", "success");
    } catch (error) {
      currentLocation = null;
      setLocationStatus(error.message, "error");
    } finally {
      locationButton.disabled = false;
      locationButton.querySelector("span").textContent = "⌖";
    }
  });

  [$("#provinceInput"), $("#districtInput")].forEach(input => input?.addEventListener("input", () => {
    if (!currentLocation) return;
    currentLocation = null;
    setLocationStatus("지역 입력 기준으로 검색합니다.");
  }));

  const renderResults = (rows, notice) => {
    resultRows = rows;
    resultPage = 0;
    resultNotice = notice || "";
    renderResultPage();
  };

  const renderResultPage = () => {
    const result = $("#recommendResults");
    if (!resultRows.length) {
      result.innerHTML = `<div class="empty-result-v4"><span>!</span><b>해당 지역에서 조건에 맞는 시설을 찾지 못했어요.</b><small>${escapeHtml(resultNotice || "지역과 운동 종목을 확인해주세요.")}</small></div>`;
      return;
    }
    const start = resultPage * pageSize;
    const visibleRows = resultRows.slice(start, start + pageSize);
    const noticeHtml = resultNotice ? `<p class="recommend-result-notice">${escapeHtml(resultNotice)}</p>` : "";
    result.innerHTML = noticeHtml + visibleRows.map((row, offset) => {
      const index = start + offset;
      const sport = String(row.sport || "fitness").toLowerCase();
      const label = app.SPORT_META[sport]?.label || row.facility_type || "운동";
      return `<article class="result-card">
        <span class="result-rank">${String(index + 1).padStart(2, "0")}</span>
        <span class="result-eyebrow">${escapeHtml(label)} PICK</span>
        <h3>${escapeHtml(row.name)}</h3>
        <p class="result-meta">${escapeHtml(row.province)} ${escapeHtml(row.district)} · ${row.indoor ? "실내" : "야외"} · 이동 ${escapeHtml(row.travel_time)}</p>
        <div class="result-score"><strong>${escapeHtml(row.score)}</strong><span>실행 적합도 / 100</span></div>
        <div class="reason-list">${(row.reasons || []).map(reason => `<span>${escapeHtml(reason)}</span>`).join("")}</div>
        ${row.operation_notice ? `<p class="result-operation-notice">운영정보: ${escapeHtml(row.operation_notice)}</p>` : ""}
        <p class="result-meta">예상 운동 가능시간 ${escapeHtml(row.available_exercise_minutes)}분</p>
        <div class="result-actions"><button type="button" data-detail-index="${index}">상세 보기</button><button type="button" class="primary-mini" data-select-index="${index}">이 운동으로 결정</button></div>
      </article>`;
    }).join("");
    result.querySelectorAll("[data-detail-index]").forEach(button => button.addEventListener("click", () => {
      const row = resultRows[Number(button.dataset.detailIndex)];
      if (row) showRecommendationDetail(row);
    }));
    result.querySelectorAll("[data-select-index]").forEach(button => button.addEventListener("click", async () => {
      const row = resultRows[Number(button.dataset.selectIndex)];
      if (row) await selectRecommendation(row, button);
    }));
    if (resultRows.length > pageSize) {
      const totalPages = Math.ceil(resultRows.length / pageSize);
      result.insertAdjacentHTML("beforeend", `<div class="recommend-pager"><button type="button" class="recommend-page-button" data-page-direction="prev" ${resultPage === 0 ? "disabled" : ""} aria-label="이전 추천 결과">‹</button><button type="button" class="recommend-page-button" data-page-direction="next" ${resultPage >= totalPages - 1 ? "disabled" : ""} aria-label="다음 추천 결과">›</button></div>`);
      result.querySelectorAll("[data-page-direction]").forEach(button => button.addEventListener("click", () => {
        resultPage += button.dataset.pageDirection === "next" ? 1 : -1;
        renderResultPage();
      }));
    }
  };

  const csrfToken = () => document.cookie.split(";").map(value => value.trim()).find(value => value.startsWith("csrftoken="))?.split("=").slice(1).join("=") || "";

  const scoreLabel = {
    base: "기본 점수",
    distance: "거리 점수",
    weather: "날씨·운동환경 보정",
    air_quality: "대기질 보정",
    operation: "운영·휴무 정보 보정",
  };

  const ensureDetailDialog = () => {
    let dialog = document.querySelector("#recommendDetailDialog");
    if (dialog) return dialog;
    document.body.insertAdjacentHTML("beforeend", `<dialog id="recommendDetailDialog" class="recommend-detail-dialog"><div class="recommend-detail-content"><button type="button" class="recommend-detail-close" data-close-detail aria-label="상세 보기 닫기">×</button><div id="recommendDetailBody"></div></div></dialog>`);
    dialog = document.querySelector("#recommendDetailDialog");
    dialog.addEventListener("click", event => { if (event.target === dialog || event.target.closest("[data-close-detail]")) dialog.close(); });
    return dialog;
  };

  const showRecommendationDetail = row => {
    const dialog = ensureDetailDialog();
    const body = dialog.querySelector("#recommendDetailBody");
    const breakdown = row.score_breakdown || {};
    const breakdownHtml = Object.entries(breakdown).filter(([key]) => key !== "final" && key !== "before_operation").map(([key, value]) => {
      const label = scoreLabel[key] || key;
      const number = Number(value);
      const formatted = Number.isFinite(number) ? `${number > 0 && key !== "base" ? "+" : ""}${number}점` : "확인 필요";
      return `<li><span>${escapeHtml(label)}</span><b>${escapeHtml(formatted)}</b></li>`;
    }).join("");
    const metrics = window.__USIM_RECOMMEND_ENVIRONMENT?.metrics || {};
    const safety = row.safety || {};
    body.innerHTML = `<span class="tiny-label accent">RECOMMEND DETAIL</span><h2>${escapeHtml(row.name)}</h2><p class="recommend-detail-address">${escapeHtml(row.address || "주소 확인 필요")}</p><div class="recommend-detail-score"><strong>${escapeHtml(row.score)}</strong><span>/ 100 최종 추천 점수</span></div><h3>점수 산출 근거</h3><ul class="score-breakdown-list">${breakdownHtml}</ul><p class="recommend-detail-formula">최종 점수: ${escapeHtml(row.score)}점</p><h3>환경 데이터</h3><div class="recommend-detail-metrics"><span>기온 ${escapeHtml(metrics.temperature_c ?? "확인 필요")}℃</span><span>습도 ${escapeHtml(metrics.humidity_percent ?? "확인 필요")}%</span><span>강수 ${escapeHtml(metrics.rain_1h_mm ?? "확인 필요")}mm</span><span>풍속 ${escapeHtml(metrics.wind_speed_mps ?? "확인 필요")}m/s</span><span>PM10 ${escapeHtml(metrics.pm10 ?? "확인 필요")}</span><span>PM2.5 ${escapeHtml(metrics.pm25 ?? "확인 필요")}</span></div><h3>안전정보</h3><div class="recommend-safety-grid"><div><b>AED</b><span>${escapeHtml(safety.aed?.label || "확인 가능한 AED 데이터 없음")}</span></div><div><b>안전점검</b><span>${escapeHtml(safety.inspection?.label || "확인 가능한 안전점검 데이터 없음")}</span></div></div>${row.operation_notice ? `<p class="result-operation-notice">운영정보: ${escapeHtml(row.operation_notice)}</p>` : ""}<p class="recommend-detail-note">${(row.reasons || []).map(reason => escapeHtml(reason)).join(" · ")}</p>`;
    if (typeof dialog.showModal === "function") dialog.showModal();
  };

  const mapUrlFor = row => {
    const name = encodeURIComponent(row.name || "운동 시설");
    const address = encodeURIComponent(row.address || row.name || "운동 시설");
    const latitude = Number(row.latitude);
    const longitude = Number(row.longitude);
    if (Number.isFinite(latitude) && Number.isFinite(longitude) && currentLocation) {
      return `https://map.kakao.com/link/from/현재 위치,${currentLocation.latitude},${currentLocation.longitude}/to/${name},${latitude},${longitude}`;
    }
    if (Number.isFinite(latitude) && Number.isFinite(longitude)) return `https://map.kakao.com/link/map/${name},${latitude},${longitude}`;
    return `https://map.kakao.com/?q=${address}`;
  };

  const selectRecommendation = async (row, button) => {
    if (button.disabled) return;
    button.disabled = true;
    button.textContent = "저장 중…";
    // 클릭 직후 빈 탭을 열어 비동기 저장 이후에도 브라우저 팝업 차단을 피한다.
    // noopener를 사용하면 일부 브라우저에서 반환 핸들이 null이 되어
    // 현재 페이지로 이동하는 fallback이 실행될 수 있으므로, 새 탭 핸들을 유지한다.
    const mapWindow = window.open("about:blank", "_blank");
    try {
      const response = await fetch("/api/selected-recommendation/", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken(), Accept: "application/json" },
        body: JSON.stringify(row),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "운동 장소 저장에 실패했습니다.");
      selectedRecommendationId = payload.id;
      button.textContent = "선택 완료";
      if (mapWindow && !mapWindow.closed) mapWindow.location.href = mapUrlFor(row);
      else alert("지도를 열 수 없습니다. 브라우저의 팝업 차단을 해제한 뒤 다시 시도해주세요.");
    } catch (error) {
      if (mapWindow && !mapWindow.closed) mapWindow.close();
      button.disabled = false;
      button.textContent = "이 운동으로 결정";
      alert(error.message);
    }
  };

  $("#recommendForm").addEventListener("submit", async event => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const sport = data.get("sport");
    if (!sport) { alert("오늘 하고 싶은 운동을 하나 선택해주세요."); return; }
    if (locationMode === "current" && !currentLocation) {
      alert("먼저 현재 위치 확인 버튼을 눌러주세요.");
      return;
    }
    const searchBasis = currentLocation ? "현재 위치 주변" : `${data.get("district")} 지역`;
    $("#recommendResults").innerHTML = `<div class="empty-result-v4"><span>…</span><b>${escapeHtml(searchBasis)}의 시설을 찾고 있어요.</b><small>선택한 운동과 날씨·대기질 데이터를 종합하는 중입니다.</small></div>`;
    const params = new URLSearchParams({
      province: data.get("province"), district: data.get("district"), sports: sport,
      available_minutes: data.get("available_minutes"), transport: data.get("transport"),
      max_travel_minutes: data.get("max_travel_minutes"),
    });
    if (currentLocation) {
      params.set("latitude", String(currentLocation.latitude));
      params.set("longitude", String(currentLocation.longitude));
    }
    try {
      const response = await fetch(`/nearby-facilities-data/?${params}`, { credentials: "same-origin", headers: { Accept: "application/json" } });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "추천 조회에 실패했습니다.");
      window.__USIM_RECOMMEND_ENVIRONMENT = payload.environment || {};
      renderResults(payload.recommendations || [], payload.notice);
    } catch (error) {
      $("#recommendResults").innerHTML = `<div class="empty-result-v4"><span>!</span><b>추천 데이터를 불러오지 못했어요.</b><small>${escapeHtml(error.message)}</small></div>`;
    }
  });
})();
