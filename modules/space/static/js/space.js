// ── 鉴权 ─────────────────────────────────────────────────────────────
const userSession = JSON.parse(localStorage.getItem("campus_user"));
if (!userSession) {
    alert("请先登录！");
    location.href = "/login";
}
const USER_ID = userSession.userId;

// ── 全局状态 ─────────────────────────────────────────────────────────
let selectedAcademicSpaceId = null;
let academicAvailable = false;           // 查询后可用才允许提交

const sportsState = {
    date: null,
    selectedSpaceIds: new Set(),         // 勾选的场地（组合预约）
    selectedHour: null,
    spacesData: [],                      // { space_id, name, slots[] }
};

// ── Toast 通知 ────────────────────────────────────────────────────────
function toast(msg, type = "info", duration = 3000) {
    const el = document.getElementById("toast");
    el.textContent = msg;
    el.className = `show ${type}`;
    setTimeout(() => { el.className = ""; }, duration);
}

// ── Tab 切换 ──────────────────────────────────────────────────────────
window.switchTab = function(name) {
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    document.querySelectorAll(".tab-btn").forEach(b => {
        b.classList.remove("active");
        b.setAttribute("aria-selected", "false");
    });
    document.getElementById(`tab-${name}`).classList.add("active");
    const btn = document.getElementById(`tbtn-${name}`);
    btn.classList.add("active");
    btn.setAttribute("aria-selected", "true");
    if (name === "mybookings") loadMyBookings();
};

// ═══════════════════════════════════════════════════════════════════════
// 学术空间
// ═══════════════════════════════════════════════════════════════════════

async function loadAcademicSpaces() {
    const res = await fetch("/api/v1/spaces/academic");
    if (!res.ok) { toast("加载学术空间失败", "error"); return; }
    const spaces = await res.json();

    const grid = document.getElementById("academic-space-grid");
    if (!spaces.length) { grid.innerHTML = "<span style='color:#aaa;'>暂无学术空间</span>"; return; }

    grid.innerHTML = spaces.map(s => `
        <div class="space-card" id="sp-ac-${s.space_id}"
             role="button" tabindex="0" aria-pressed="false"
             aria-label="选择 ${s.name}"
             onclick="selectAcademicSpace('${s.space_id}', '${s.name}')"
             onkeydown="if(event.key==='Enter'||event.key===' ')selectAcademicSpace('${s.space_id}','${s.name}')">
            <h3>${s.name}</h3>
            <p>${s.description || "学术空间"}</p>
            <span class="badge badge-cap">容量 ${s.capacity} 人</span>
        </div>
    `).join("");
}

window.selectAcademicSpace = function(spaceId, name) {
    selectedAcademicSpaceId = spaceId;
    academicAvailable = false;
    document.getElementById("btn-book-academic").disabled = true;
    document.getElementById("ac-avail-result").innerHTML = "";
    document.getElementById("ac-confirm-hint").textContent = `已选：${name}，请查询可用性后预约`;

    document.querySelectorAll(".space-card").forEach(el => {
        el.classList.remove("selected");
        el.setAttribute("aria-pressed", "false");
    });
    const card = document.getElementById(`sp-ac-${spaceId}`);
    if (card) { card.classList.add("selected"); card.setAttribute("aria-pressed", "true"); }
};

window.checkAcademicAvailability = async function() {
    if (!selectedAcademicSpaceId) { toast("请先选择空间", "error"); return; }
    const start = document.getElementById("ac-start").value;
    const end   = document.getElementById("ac-end").value;
    if (!start || !end) { toast("请填写完整的开始和结束时间", "error"); return; }

    const resultEl = document.getElementById("ac-avail-result");
    resultEl.innerHTML = "<span style='color:#888;'>查询中...</span>";

    const params = new URLSearchParams({ start_time: start, end_time: end });
    const res = await fetch(`/api/v1/spaces/academic/${selectedAcademicSpaceId}/check?${params}`);

    if (!res.ok) {
        const err = await res.json();
        resultEl.innerHTML = `<div class="avail-result avail-no">⚠️ ${err.detail}</div>`;
        academicAvailable = false;
        document.getElementById("btn-book-academic").disabled = true;
        return;
    }

    const data = await res.json();
    if (data.available) {
        const buf_s = new Date(data.buffered_start).toLocaleTimeString("zh", {hour:"2-digit", minute:"2-digit"});
        const buf_e = new Date(data.buffered_end).toLocaleTimeString("zh", {hour:"2-digit", minute:"2-digit"});
        resultEl.innerHTML = `<div class="avail-result avail-ok">✅ 时段可用，可以预约！</div>`;
        academicAvailable = true;
        document.getElementById("btn-book-academic").disabled = false;
    } else {
        resultEl.innerHTML = `<div class="avail-result avail-no">❌ 该时段已被占用，请选择其他时间</div>`;
        academicAvailable = false;
        document.getElementById("btn-book-academic").disabled = true;
    }
};

window.bookAcademic = async function() {
    if (!academicAvailable || !selectedAcademicSpaceId) return;
    const start = document.getElementById("ac-start").value;
    const end   = document.getElementById("ac-end").value;

    const btn = document.getElementById("btn-book-academic");
    btn.disabled = true;
    btn.textContent = "预约中...";

    const res = await fetch("/api/v1/spaces/academic/book", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            space_id: selectedAcademicSpaceId,
            user_id: USER_ID,
            start_time: start,
            end_time: end,
        }),
    });

    const data = await res.json();
    if (res.ok) {
        toast("✅ 预约成功！", "success", 3000);
        document.getElementById("ac-avail-result").innerHTML =
            `<div class="avail-result avail-ok">✅ 预约成功！</div>`;
        academicAvailable = false;
    } else {
        toast(`预约失败：${data.detail}`, "error", 4000);
        document.getElementById("ac-avail-result").innerHTML =
            `<div class="avail-result avail-no">❌ ${data.detail}</div>`;
    }

    btn.textContent = "确认预约";
    btn.disabled = true;
};

// ═══════════════════════════════════════════════════════════════════════
// 体育设施
// ═══════════════════════════════════════════════════════════════════════

window.loadSportsView = async function() {
    const dateVal = document.getElementById("sp-date").value;
    if (!dateVal) { toast("请先选择日期", "error"); return; }
    sportsState.date = dateVal;
    sportsState.selectedSpaceIds.clear();
    sportsState.selectedHour = null;
    document.getElementById("sp-confirm-card").style.display = "none";

    const listEl = document.getElementById("sports-space-list");
    listEl.innerHTML = "<span style='color:#aaa;'>加载中...</span>";

    const res = await fetch("/api/v1/spaces/sports");
    if (!res.ok) { toast("加载体育设施失败", "error"); return; }
    const spaces = await res.json();

    sportsState.spacesData = [];

    // 并发拉取各场地 slots
    const slotResults = await Promise.all(
        spaces.map(s =>
            fetch(`/api/v1/spaces/sports/${s.space_id}/slots?slot_date=${dateVal}`)
                .then(r => r.ok ? r.json() : [])
        )
    );

    spaces.forEach((s, i) => {
        sportsState.spacesData.push({ ...s, slots: slotResults[i] });
    });

    renderSportsList();
};

function renderSportsList() {
    const listEl = document.getElementById("sports-space-list");
    if (!sportsState.spacesData.length) {
        listEl.innerHTML = "<span style='color:#aaa;'>暂无体育设施</span>";
        return;
    }

    listEl.innerHTML = sportsState.spacesData.map(s => {
        const checked = sportsState.selectedSpaceIds.has(s.space_id) ? "checked" : "";
        return `
        <div class="card" style="margin-bottom:12px;">
            <div style="display:flex; align-items:center; gap:10px; margin-bottom:10px; flex-wrap:wrap;">
                <label class="combine-check" for="chk-${s.space_id}">
                    <input type="checkbox" id="chk-${s.space_id}" ${checked}
                           ${s.is_combinable ? "" : "title='该场地不支持组合预约'"}
                           onchange="toggleSportsSpace('${s.space_id}', ${s.is_combinable})"
                           aria-label="选择 ${s.name}">
                    <strong>${s.name}</strong>
                </label>
                ${s.is_combinable ? '<span class="badge badge-comb">支持组合</span>' : ""}
                <span class="badge badge-cap">容量 ${s.capacity} 人</span>
            </div>
            <div class="slot-grid" id="slots-${s.space_id}" aria-label="${s.name} 时段">
                ${renderSlotCells(s.space_id, s.slots)}
            </div>
        </div>`;
    }).join("");
}

function renderSlotCells(spaceId, slots) {
    return slots.map(slot => {
        const cls = slot.available ? "available" : "taken";
        const label = slot.available ? "可预约" : "已占用";
        const isSelected = sportsState.selectedHour === slot.hour
            && sportsState.selectedSpaceIds.has(spaceId);
        const selCls = isSelected ? " selected" : "";
        const clickable = slot.available
            ? `onclick="selectSportsSlot(${slot.hour})"` : "";
        return `
            <div class="slot-cell ${cls}${selCls}" ${clickable}
                 role="${slot.available ? 'button' : 'img'}"
                 aria-label="${slot.hour}:00 ${label}"
                 tabindex="${slot.available ? 0 : -1}"
                 onkeydown="if(event.key==='Enter')selectSportsSlot(${slot.hour})">
                ${slot.hour}:00
                <div class="slot-label">${label}</div>
            </div>`;
    }).join("");
}

window.toggleSportsSpace = function(spaceId, isCombinable) {
    const chk = document.getElementById(`chk-${spaceId}`);
    if (chk.checked) {
        // 若已有选择且当前或目标不支持组合，则不允许多选
        if (sportsState.selectedSpaceIds.size > 0 && !isCombinable) {
            toast("该场地不支持组合预约", "error");
            chk.checked = false;
            return;
        }
        sportsState.selectedSpaceIds.add(spaceId);
    } else {
        sportsState.selectedSpaceIds.delete(spaceId);
    }
    sportsState.selectedHour = null;
    updateSportsConfirmPanel();
    renderSportsList();
};

window.selectSportsSlot = function(hour) {
    if (!sportsState.selectedSpaceIds.size) {
        toast("请先勾选至少一个场地", "error");
        return;
    }
    sportsState.selectedHour = hour;
    updateSportsConfirmPanel();
    renderSportsList();
};

function updateSportsConfirmPanel() {
    const card = document.getElementById("sp-confirm-card");
    const info = document.getElementById("sp-confirm-info");

    if (!sportsState.selectedSpaceIds.size || sportsState.selectedHour === null) {
        card.style.display = "none";
        return;
    }

    const names = [...sportsState.selectedSpaceIds].map(id => {
        const s = sportsState.spacesData.find(x => x.space_id === id);
        return s ? s.name : id;
    });

    info.innerHTML = `
        <strong>场地：</strong>${names.join(" + ")}<br>
        <strong>日期：</strong>${sportsState.date}<br>
        <strong>时段：</strong>${sportsState.selectedHour}:00 – ${sportsState.selectedHour + 1}:00
        ${sportsState.selectedSpaceIds.size > 1 ? '<span class="badge badge-comb" style="margin-left:8px;">组合预约</span>' : ""}
    `;
    card.style.display = "block";
}

window.clearSportsSelection = function() {
    sportsState.selectedSpaceIds.clear();
    sportsState.selectedHour = null;
    document.getElementById("sp-confirm-card").style.display = "none";
    renderSportsList();
};

window.bookSports = async function() {
    if (!sportsState.selectedSpaceIds.size || sportsState.selectedHour === null) return;

    const btn = document.getElementById("btn-book-sports");
    btn.disabled = true;
    btn.textContent = "预约中...";

    const res = await fetch("/api/v1/spaces/sports/book", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            space_ids: [...sportsState.selectedSpaceIds],
            user_id: USER_ID,
            slot_date: sportsState.date,
            slot_hour: sportsState.selectedHour,
        }),
    });

    const data = await res.json();
    if (res.ok) {
        const idList = data.booking_ids.join(", ");
        toast(`✅ 预约成功！凭证：${idList}`, "success", 4000);
        clearSportsSelection();
        loadSportsView();  // 刷新 slot 状态
    } else {
        toast(`预约失败：${data.detail}`, "error", 4000);
    }

    btn.disabled = false;
    btn.textContent = "确认预约";
};

// ═══════════════════════════════════════════════════════════════════════
// 我的预约
// ═══════════════════════════════════════════════════════════════════════

window.loadMyBookings = async function() {
    const res = await fetch(`/api/v1/spaces/bookings/user/${USER_ID}`);
    if (!res.ok) { toast("加载预约记录失败", "error"); return; }
    const data = await res.json();

    // 学术空间
    const acEl = document.getElementById("my-academic-bookings");
    if (!data.academic.length) {
        acEl.innerHTML = "<span style='color:#aaa;'>暂无学术空间预约</span>";
    } else {
        acEl.innerHTML = data.academic.map(b => {
            const s = new Date(b.actual_start).toLocaleString("zh", {month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"});
            const e = new Date(b.actual_end).toLocaleTimeString("zh", {hour:"2-digit", minute:"2-digit"});
            return `
                <div class="booking-item">
                    <div class="booking-info">
                        <strong>${b.space_name || b.space_id}</strong><br>
                        ${s} – ${e}
                        <span style="font-size:0.85em; color:#888; margin-left:8px;">${b.booking_id}</span>
                    </div>
                    <button class="btn btn-danger btn-sm"
                            onclick="cancelBooking('${b.booking_id}', 'academic')"
                            aria-label="取消 ${b.space_name || b.space_id} 的预约">
                        取消
                    </button>
                </div>`;
        }).join("");
    }

    // 体育设施
    const spEl = document.getElementById("my-sports-bookings");
    if (!data.sports.length) {
        spEl.innerHTML = "<span style='color:#aaa;'>暂无体育设施预约</span>";
    } else {
        spEl.innerHTML = data.sports.map(b => {
            const names = b.space_ids.join(" + ");
            const isGroup = b.space_ids.length > 1;
            return `
                <div class="booking-item sports">
                    <div class="booking-info">
                        <strong>${names}</strong>
                        ${isGroup ? '<span class="badge badge-comb" style="margin-left:6px;">组合</span>' : ""}
                        <br>
                        ${b.slot_date} &nbsp; ${b.slot_hour}:00 – ${b.slot_hour + 1}:00
                        <span style="font-size:0.85em; color:#888; margin-left:8px;">${b.booking_ids[0]}</span>
                    </div>
                    <button class="btn btn-danger btn-sm"
                            onclick="cancelBooking('${b.booking_ids[0]}', 'sports')"
                            aria-label="取消 ${names} 的预约">
                        取消${isGroup ? "（整组）" : ""}
                    </button>
                </div>`;
        }).join("");
    }
};

window.cancelBooking = async function(bookingId, type) {
    if (!confirm(`确认取消该预约？${type === "sports" ? "\n（组合预约将整组取消）" : ""}`)) return;

    const res = await fetch(`/api/v1/spaces/bookings/${bookingId}`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: USER_ID }),
    });

    const data = await res.json();
    if (res.ok) {
        toast("已成功取消预约", "success");
        loadMyBookings();
    } else {
        toast(`取消失败：${data.detail}`, "error");
    }
};

// ── 初始化 ────────────────────────────────────────────────────────────
(function init() {
    // 默认日期设为今天
    const today = new Date().toISOString().split("T")[0];
    document.getElementById("sp-date").value = today;
    document.getElementById("sp-date").min = today;

    // 默认时间设为当前最近整点后 30 分钟
    const now = new Date();
    now.setMinutes(Math.ceil(now.getMinutes() / 30) * 30, 0, 0);
    const pad = n => String(n).padStart(2, "0");
    const localNow = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
    const endTime = new Date(now.getTime() + 60 * 60 * 1000);
    const localEnd = `${endTime.getFullYear()}-${pad(endTime.getMonth()+1)}-${pad(endTime.getDate())}T${pad(endTime.getHours())}:${pad(endTime.getMinutes())}`;
    document.getElementById("ac-start").value = localNow;
    document.getElementById("ac-end").value = localEnd;
    document.getElementById("ac-start").min = localNow;

    loadAcademicSpaces();
})();
