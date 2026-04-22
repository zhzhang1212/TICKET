function initSpacePanels(verifiedAdminKey) {
    const navGrid = document.querySelector("nav.grid-container");
    const roomSection = document.getElementById("room-management-section");
    const venueSection = document.getElementById("venue-management-section");
    const btnRoomMgr = document.getElementById("btn-room-mgr");
    const btnVenueMgr = document.getElementById("btn-venue-mgr");
    const btnRoomBack = document.getElementById("btn-room-back");
    const btnVenueBack = document.getElementById("btn-venue-back");
    const roomContainer = document.getElementById("room-list-container");
    const venueContainer = document.getElementById("venue-list-container");

    const showSection = (section) => {
        if (navGrid) navGrid.style.display = "none";
        if (section) section.style.display = "block";
    };

    const hideSection = (section) => {
        if (section) section.style.display = "none";
        if (navGrid) navGrid.style.display = "grid";
    };

    const fmtDate = (d) => {
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, "0");
        const day = String(d.getDate()).padStart(2, "0");
        return `${y}-${m}-${day}`;
    };

    const DEFAULT_ROOM_HOURS = Array.from({ length: 15 }, (_, i) => i + 8);
    const VENUE_HOURS = Array.from({ length: 15 }, (_, i) => i + 8);
    let roomSelectedDate = fmtDate(new Date());
    let venueSelectedDate = fmtDate(new Date());

    const getAdminKey = () => {
        const input = document.getElementById("admin-key-input");
        const inputKey = (input && input.value ? input.value.trim() : "");
        let cachedKey = "";
        try { cachedKey = window.localStorage.getItem("fsm_admin_key") || ""; } catch (_) {}
        const key = inputKey || cachedKey || verifiedAdminKey;
        if (input && !input.value && key) {
            input.value = key;
        }
        return key;
    };

    const fetchAdminBookings = async () => {
        const doFetch = (key) => fetch("/api/v1/spaces/admin/bookings", {
            headers: { "X-Admin-Key": key },
        });

        let adminKey = getAdminKey();
        let resp = await doFetch(adminKey);
        if (resp.status !== 403) {
            return resp;
        }

        const manualKey = window.prompt("请输入管理员密钥以加载预约总览", adminKey || "");
        if (!manualKey || !manualKey.trim()) {
            return resp;
        }

        adminKey = manualKey.trim();
        window.localStorage.setItem("fsm_admin_key", adminKey);
        const input = document.getElementById("admin-key-input");
        if (input) {
            input.value = adminKey;
        }
        return doFetch(adminKey);
    };

    const renderMatrixTable = (rows, headers, title, subtitle) => {
        return `
            <div style="margin-bottom:10px;">
                <h3 style="margin:0; color:#1565c0;">${title}</h3>
                <p style="margin:6px 0 0; color:#666; font-size:0.9em;">${subtitle}</p>
            </div>
            <div style="overflow:auto; border-radius:8px; border:1px solid #d9e2ef; background:#fff;">
                <table style="width:100%; min-width:1100px; border-collapse:collapse; font-size:0.86em;">
                    <thead>
                        <tr style="background:#eef4ff;">
                            <th style="position:sticky; left:0; background:#eef4ff; z-index:2; border:1px solid #d9e2ef; padding:8px; min-width:180px; text-align:left;">资源</th>
                            ${headers.map((h) => `<th style="border:1px solid #d9e2ef; padding:8px; min-width:90px;">${h}</th>`).join("")}
                        </tr>
                    </thead>
                    <tbody>
                        ${rows}
                    </tbody>
                </table>
            </div>
        `;
    };

    const buildDateToolbar = (dates, selected, prefix) => {
        if (!dates.length) return "";
        return `
            <div style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:10px;">
                ${dates.map((d) => `
                    <button type="button" data-${prefix}-date="${d}"
                        style="padding:6px 10px; border-radius:16px; border:1px solid ${d === selected ? '#1565c0' : '#c7d2e3'}; background:${d === selected ? '#e8f1ff' : '#fff'}; color:${d === selected ? '#1565c0' : '#455a64'}; cursor:pointer; font-size:0.85em;">
                        ${d}
                    </button>
                `).join("")}
            </div>
        `;
    };

    const loadRoomOverview = async () => {
        if (!roomContainer) return;
        roomContainer.innerHTML = '<p style="color:#888;">正在加载房间矩阵...</p>';

        try {
            const [spaceResp, bookingResp] = await Promise.all([
                fetch("/api/v1/spaces/academic"),
                fetchAdminBookings(),
            ]);

            if (!spaceResp.ok || !bookingResp.ok) {
                roomContainer.innerHTML = '<p style="color:red;">加载失败，请稍后重试。</p>';
                return;
            }

            const spaces = await spaceResp.json();
            const bookingData = await bookingResp.json();
            const rows = (bookingData.academic || []).filter((b) => b.status === "confirmed");

            const bookingDates = [...new Set(rows.map((b) => (b.actual_start || "").slice(0, 10)).filter(Boolean))].sort();
            if (bookingDates.length > 0 && !bookingDates.includes(roomSelectedDate)) {
                roomSelectedDate = bookingDates[0];
            }
            const dateOptions = [...new Set([fmtDate(new Date()), ...bookingDates])].sort();
            const dayStart = new Date(`${roomSelectedDate}T00:00:00`);

            // 学术空间支持全天预约，这里动态扩展小时列，避免夜间预约在大盘“看不见”。
            const bookedHours = new Set();
            rows
                .filter((b) => (b.actual_start || "").slice(0, 10) === roomSelectedDate)
                .forEach((b) => {
                    const bStart = new Date(b.actual_start);
                    const bEnd = new Date(b.actual_end);
                    const startHour = Math.max(0, Math.floor(bStart.getHours()));
                    const endHour = Math.min(24, Math.ceil(bEnd.getHours()));
                    for (let h = startHour; h < endHour; h += 1) {
                        bookedHours.add(h);
                    }
                });
            const roomHours = [...new Set([...DEFAULT_ROOM_HOURS, ...Array.from(bookedHours)])]
                .sort((a, b) => a - b);

            const tableRows = spaces.map((s) => {
                const related = rows.filter((b) => b.space_id === s.space_id);
                const cells = roomHours.map((hour) => {
                    const slotStart = new Date(dayStart.getTime() + hour * 60 * 60 * 1000);
                    const slotEnd = new Date(slotStart.getTime() + 60 * 60 * 1000);
                    const hit = related.filter((b) => {
                        const bStart = new Date(b.actual_start);
                        const bEnd = new Date(b.actual_end);
                        return bStart < slotEnd && bEnd > slotStart;
                    });

                    if (hit.length === 0) {
                        return '<td style="border:1px solid #e5eaf3; background:#eaf7ea; color:#2e7d32; text-align:center; padding:6px;">空闲</td>';
                    }

                    const users = [...new Set(hit.map((x) => x.user_id || "未知"))].join("/");
                    const detail = hit.map((x) => `${x.user_id || "未知"} ${x.actual_start.slice(11, 16)}-${x.actual_end.slice(11, 16)}`).join("; ");
                    return `<td title="${detail}" style="border:1px solid #e5eaf3; background:#fdeaea; color:#c62828; text-align:center; padding:6px; font-weight:600;">${users}</td>`;
                }).join("");

                return `
                    <tr>
                        <td style="position:sticky; left:0; background:#fff; z-index:1; border:1px solid #e5eaf3; padding:8px;">
                            <strong style="color:#1a237e;">${s.name || s.space_id}</strong><br>
                            <span style="font-size:0.82em; color:#777;">${s.space_id}</span>
                        </td>
                        ${cells}
                    </tr>
                `;
            }).join("");

            roomContainer.innerHTML = `
                ${buildDateToolbar(dateOptions, roomSelectedDate, "room")}
                ${renderMatrixTable(
                tableRows,
                roomHours.map((h) => `${h}:00`),
                "房间预约总览",
                `日期：${roomSelectedDate}（每行一个房间，格子内为预约人；鼠标悬停可看预约时段）`
                )}
            `;

            roomContainer.querySelectorAll("[data-room-date]").forEach((btn) => {
                btn.addEventListener("click", () => {
                    const nextDate = btn.getAttribute("data-room-date");
                    if (!nextDate || nextDate === roomSelectedDate) return;
                    roomSelectedDate = nextDate;
                    loadRoomOverview();
                });
            });
        } catch (e) {
            console.error("加载房间状态失败", e);
            roomContainer.innerHTML = '<p style="color:red;">网络异常，无法加载房间状态。</p>';
        }
    };

    const loadVenueOverview = async () => {
        if (!venueContainer) return;
        venueContainer.innerHTML = '<p style="color:#888;">正在加载场地矩阵...</p>';

        try {
            const [spaceResp, bookingResp] = await Promise.all([
                fetch("/api/v1/spaces/sports"),
                fetchAdminBookings(),
            ]);

            if (!spaceResp.ok || !bookingResp.ok) {
                venueContainer.innerHTML = '<p style="color:red;">加载失败，请稍后重试。</p>';
                return;
            }

            const spaces = await spaceResp.json();
            const bookingData = await bookingResp.json();
            const bookings = (bookingData.sports || []).filter((b) => b.status === "confirmed");

            const bookingDates = [...new Set(bookings.map((b) => b.slot_date).filter(Boolean))].sort();
            if (bookingDates.length > 0 && !bookingDates.includes(venueSelectedDate)) {
                venueSelectedDate = bookingDates[0];
            }
            const dateOptions = [...new Set([fmtDate(new Date()), ...bookingDates])].sort();

            const userMap = new Map();
            bookings.forEach((b) => {
                (b.space_ids || []).forEach((sid) => {
                    userMap.set(`${sid}|${b.slot_date}|${b.slot_hour}`, {
                        user_id: b.user_id || "未知",
                        booking_id: b.group_booking_id || (b.booking_ids ? b.booking_ids[0] : "--"),
                    });
                });
            });

            const slotRespList = await Promise.all(
                spaces.map((s) => fetch(`/api/v1/spaces/sports/${s.space_id}/slots?slot_date=${venueSelectedDate}`))
            );
            const slotDataList = await Promise.all(slotRespList.map(async (r) => (r.ok ? r.json() : [])));

            const tableRows = spaces.map((s, idx) => {
                const slots = slotDataList[idx] || [];
                const slotMap = new Map(slots.map((x) => [x.hour, x.available]));

                const cells = VENUE_HOURS.map((hour) => {
                    const key = `${s.space_id}|${venueSelectedDate}|${hour}`;
                    const available = slotMap.get(hour);
                    const booked = available === false;
                    if (!booked) {
                        return '<td style="border:1px solid #e5eaf3; background:#eaf7ea; color:#2e7d32; text-align:center; padding:6px;">空闲</td>';
                    }

                    const info = userMap.get(key);
                    const user = info ? info.user_id : "未知";
                    const tip = info ? `预约人: ${info.user_id} | 订单: ${info.booking_id}` : "预约人未知";
                    return `<td title="${tip}" style="border:1px solid #e5eaf3; background:#fdeaea; color:#c62828; text-align:center; padding:6px; font-weight:600;">${user}</td>`;
                }).join("");

                return `
                    <tr>
                        <td style="position:sticky; left:0; background:#fff; z-index:1; border:1px solid #e5eaf3; padding:8px;">
                            <strong style="color:#1a237e;">${s.name || s.space_id}</strong><br>
                            <span style="font-size:0.82em; color:#777;">${s.space_id}</span>
                        </td>
                        ${cells}
                    </tr>
                `;
            }).join("");

            venueContainer.innerHTML = `
                ${buildDateToolbar(dateOptions, venueSelectedDate, "venue")}
                ${renderMatrixTable(
                tableRows,
                VENUE_HOURS.map((h) => `${h}:00`),
                "场地预约总览",
                `日期：${venueSelectedDate}（每行一个场地，格子内为预约人；鼠标悬停可看订单信息）`
                )}
            `;

            venueContainer.querySelectorAll("[data-venue-date]").forEach((btn) => {
                btn.addEventListener("click", () => {
                    const nextDate = btn.getAttribute("data-venue-date");
                    if (!nextDate || nextDate === venueSelectedDate) return;
                    venueSelectedDate = nextDate;
                    loadVenueOverview();
                });
            });
        } catch (e) {
            console.error("加载场地状态失败", e);
            venueContainer.innerHTML = '<p style="color:red;">网络异常，无法加载场地状态。</p>';
        }
    };

    if (btnRoomMgr) {
        const open = () => {
            showSection(roomSection);
            loadRoomOverview();
        };
        btnRoomMgr.onclick = open;
        btnRoomMgr.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") open(); });
    }
    if (btnVenueMgr) {
        const open = () => {
            showSection(venueSection);
            loadVenueOverview();
        };
        btnVenueMgr.onclick = open;
        btnVenueMgr.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") open(); });
    }
    if (btnRoomBack) btnRoomBack.onclick = () => hideSection(roomSection);
    if (btnVenueBack) btnVenueBack.onclick = () => hideSection(venueSection);
}

function initFsmPanel() {
    const mainDashboard = document.getElementById("main-dashboard");
    const btnTicketMgr = document.getElementById("btn-ticket-mgr");
    const ticketManagementSection = document.getElementById("ticket-management-section");

    const listContainer = document.getElementById("event-list-container");
    const detailPanel = document.getElementById("detail-panel");
    const btnShowPublish = document.getElementById("btn-show-publish");
    const btnClosePanel = document.getElementById("btn-close-panel");

    const editEventId = document.getElementById("edit-event-id"); // Hidden field to track if editing
    const editEventSlotId = document.getElementById("edit-event-slot-id");
    const editEventName = document.getElementById("edit-event-name");
    const editEventDesc = document.getElementById("edit-event-desc");
    const editEventCapacity = document.getElementById("edit-event-capacity");
    const editEventStartTime = document.getElementById("edit-event-start-time");
    const editEventEndTime = document.getElementById("edit-event-end-time");
    const btnPublishEvent = document.getElementById("btn-publish-event");

    const eventDesc = document.getElementById("event-desc");
    const eventStockInfo = document.getElementById("event-stock-info");
    const recordsContainer = document.getElementById("records-container");
    const eventStats = document.getElementById("event-stats");
    const recordsView = document.getElementById("records-view");
    const btnRefresh = document.getElementById("btn-refresh");
    const labelForCapacity = document.getElementById("label-for-capacity");
    const capacityHint = document.getElementById("capacity-hint");

    let currentEvents = [];

    const navGrid = document.querySelector("nav.grid-container");
    const btnTicketBack = document.getElementById("btn-ticket-back");

    if (btnTicketMgr) {
        const openTicket = () => {
            if (navGrid) navGrid.style.display = "none";
            if (ticketManagementSection) ticketManagementSection.style.display = "block";
            loadEvents();
        };
        btnTicketMgr.onclick = openTicket;
        btnTicketMgr.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") openTicket(); });
    }

    if (btnTicketBack) {
        btnTicketBack.onclick = () => {
            if (ticketManagementSection) ticketManagementSection.style.display = "none";
            if (detailPanel) detailPanel.style.display = "none";
            if (navGrid) navGrid.style.display = "grid";
        };
    }

    const loadEvents = async () => {
        try {
            const r = await fetch("/api/v1/events/");
            if (r.ok) {
                currentEvents = await r.json();
                renderEventList(currentEvents);
            }
        } catch (e) {
            console.error("Failed to load events", e);
        }
    };

    const renderEventList = (events) => {
        if (!listContainer) return;
        listContainer.innerHTML = "";
        if (events.length === 0) {
            listContainer.innerHTML = '<p style="color:#888;">暂无活动，请发布新活动。</p>';
            return;
        }
        events.forEach(ev => {
            const card = document.createElement("div");
            card.className = "card";
            card.setAttribute("tabindex", "0");

            const h3 = document.createElement("h3");
            h3.textContent = `🎫 ${ev.event_name || ev.slot_id}`;

            const p = document.createElement("p");
            p.style.color = "#555";
            p.textContent = ev.description || "暂无描述";

            const meta = document.createElement("div");
            meta.style.cssText = "font-size:0.9em; margin-top:10px;";
            meta.innerHTML = `<span>有效票数：<strong>${ev.total_capacity}</strong></span> | <span>剩余：<strong style="color:#c62828">${ev.remaining_stock}</strong></span>`;

            card.appendChild(h3);
            card.appendChild(p);
            card.appendChild(meta);
            card.onclick = () => openEditPanel(ev);
            card.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") openEditPanel(ev); });
            listContainer.appendChild(card);
        });
    };

    const openPublishPanel = () => {
        if (editEventId) editEventId.value = "NEW";
        if (editEventSlotId) {
            editEventSlotId.value = "";
            editEventSlotId.disabled = false;
        }
        if (editEventName) editEventName.value = "";
        if (editEventDesc) editEventDesc.value = "";
        if (editEventCapacity) editEventCapacity.value = 100;
        
        if (labelForCapacity) labelForCapacity.innerHTML = `初始有效票数: <input type="number" id="edit-event-capacity" style="width:100%; padding:5px; border:1px solid #ccc; border-radius:4px; box-sizing:border-box;" value="100">`;
        if (capacityHint) capacityHint.innerText = "新建活动，填入初始化总释放票数。";
        
        if (eventStats) eventStats.style.display = "none";
        if (recordsView) recordsView.style.display = "none";
        if (detailPanel) detailPanel.style.display = "block";
        if (listContainer) listContainer.style.display = "none";
    };

    const openEditPanel = (ev) => {
        if (editEventId) editEventId.value = ev.slot_id;
        if (editEventSlotId) {
            editEventSlotId.value = ev.slot_id;
            editEventSlotId.disabled = true;
        }
        if (editEventName) editEventName.value = ev.event_name;
        if (editEventDesc) editEventDesc.value = ev.description;
        
        if (labelForCapacity) labelForCapacity.innerHTML = `有效票数增减: <input type="number" id="edit-event-capacity" style="width:100%; padding:5px; border:1px solid #ccc; border-radius:4px; box-sizing:border-box;" value="0">`;
        if (capacityHint) capacityHint.innerText = "增发票数填正数，削减票数填负数，注意剩余票数会同步增减。由于已有票数不支持直接重写覆盖。";
        
        if (eventDesc) eventDesc.innerText = ev.description;
        if (eventStockInfo) eventStockInfo.innerText = `总容量：${ev.total_capacity} | 剩余可购：${ev.remaining_stock}`;
        if (eventStats) eventStats.style.display = "block";
        
        renderRecords(ev.successful_bookings);
        if (recordsView) recordsView.style.display = "block";
        if (detailPanel) detailPanel.style.display = "block";
        if (listContainer) listContainer.style.display = "none";
    };

    const renderRecords = (bookings) => {
        if (!recordsContainer) return;
        recordsContainer.innerHTML = "";
        if (bookings && bookings.length > 0) {
            const sorted = bookings.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
            sorted.forEach((record, index) => {
                const li = document.createElement("li");
                li.className = "record-item";
                
                // Color code status
                let statusColor = "#666";
                let status = record.status || "未知";
                if (status.includes("已支付")) statusColor = "#4caf50";
                else if (status.includes("待支付")) statusColor = "#ff9800";
                else if (status.includes("已取消")) statusColor = "#9e9e9e";
                else if (status.includes("违约")) statusColor = "#f44336";

                const left = document.createElement("span");
                const uid = document.createElement("span");
                uid.style.color = "#1565c0";
                uid.textContent = record.user_id;
                const vchr = document.createElement("span");
                vchr.style.cssText = "font-size:0.85em; color:#555;";
                vchr.textContent = record.voucher;
                left.innerHTML = `<strong>No.${index + 1}</strong> 用户: `;
                left.appendChild(uid);
                left.append("  凭证号: ");
                left.appendChild(vchr);

                const right = document.createElement("div");
                right.style.cssText = "display:flex; flex-direction:column; align-items:flex-end;";
                const ts = document.createElement("span");
                ts.className = "timestamp";
                ts.textContent = record.timestamp;
                const st = document.createElement("span");
                st.style.cssText = `font-size:0.85em; font-weight:bold; color:${statusColor}; margin-top:4px;`;
                st.textContent = status;
                right.appendChild(ts);
                right.appendChild(st);

                li.appendChild(left);
                li.appendChild(right);
                recordsContainer.appendChild(li);
            });
        } else {
            recordsContainer.innerHTML = '<li class="record-item" style="color: #999;">暂无抢票成功记录...</li>';
        }
    };

    if(btnPublishEvent) {
        btnPublishEvent.onclick = async () => {
            const adminKeyInput = document.getElementById("admin-key-input");
            const adminKey = adminKeyInput ? adminKeyInput.value.trim() : "";
            
            if (!adminKey) {
                alert("❌ 请先输入管理员密钥！");
                return;
            }
            window.localStorage.setItem("fsm_admin_key", adminKey);

            const mode = editEventId ? editEventId.value : "";
            const slot_id = editEventSlotId ? editEventSlotId.value : "";
            const name = editEventName ? editEventName.value : "";
            const desc = editEventDesc ? editEventDesc.value : "";
            // get currently rendered capacity input
            const capacityInput = document.getElementById("edit-event-capacity");
            const capValue = capacityInput ? (parseInt(capacityInput.value) || 0) : 0;
            const startTime = editEventStartTime && editEventStartTime.value ? editEventStartTime.value : null;
            const endTime = editEventEndTime && editEventEndTime.value ? editEventEndTime.value : null;

            if (!slot_id || !name) {
                alert("请填写完整的活动ID与名称！");
                return;
            }

            if (mode === "NEW") {
                // POST to create
                const r = await fetch("/api/v1/events/", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-Admin-Key": adminKey
                    },
                    body: JSON.stringify({
                        slot_id: slot_id,
                        event_name: name,
                        description: desc,
                        capacity: capValue,
                        start_time: startTime,
                        end_time: endTime
                    })
                });
                if (r.ok) {
                    alert("✅ 发布成功！");
                    if (detailPanel) detailPanel.style.display = "none";
                    if (listContainer) listContainer.style.display = "grid";
                    loadEvents();
                    if (adminKeyInput) adminKeyInput.value = ""; // Clear key after success
                } else {
                    const err = await r.json();
                    alert("❌ 发布失败：" + (err.detail || JSON.stringify(err)));
                }
            } else {
                // PATCH to update
                const payload = {
                    event_name: name,
                    description: desc
                };
                if (startTime) payload.start_time = startTime;
                if (endTime) payload.end_time = endTime;
                if (capValue !== 0) {
                    payload.capacity_delta = capValue;
                }
                const r = await fetch(`/api/v1/events/${slot_id}`, {
                    method: "PATCH",
                    headers: {
                        "Content-Type": "application/json",
                        "X-Admin-Key": adminKey
                    },
                    body: JSON.stringify(payload)
                });
                if (r.ok) {
                    alert("✅ 更改保存成功！");
                    if (detailPanel) detailPanel.style.display = "none";
                    if (listContainer) listContainer.style.display = "grid";
                    loadEvents();
                    if (adminKeyInput) adminKeyInput.value = ""; // Clear key after success
                } else {
                    const err = await r.json();
                    alert("❌ 更新失败: " + (err.detail || JSON.stringify(err)));
                }
            }
        };
    }

    if(btnClosePanel) {
        btnClosePanel.onclick = () => {
            if (detailPanel) detailPanel.style.display = "none";
            if (listContainer) listContainer.style.display = "grid";
            loadEvents();
        };
    }

    if(btnRefresh) {
        btnRefresh.onclick = async () => {
            const slot_id = editEventSlotId ? editEventSlotId.value : "";
            if(slot_id && slot_id !== "NEW") {
                try {
                    const r = await fetch(`/api/v1/events/${slot_id}`);
                    if(r.ok) {
                        const ev = await r.json();
                        openEditPanel(ev);
                    }
                } catch(e) { console.error(e); }
            }
        };
    }

    if(btnShowPublish) {
        btnShowPublish.onclick = openPublishPanel;
    }
}

async function verifyAdminAccessBeforeEnter() {
    const app = document.getElementById("app");
    const gate = document.getElementById("auth-gate");
    const form = document.getElementById("auth-form");
    const keyInput = document.getElementById("gate-key-input");
    const errorEl = document.getElementById("auth-error");
    const submitBtn = form ? form.querySelector("button[type=submit]") : null;

    // 尝试读取上次缓存的密钥
    let cached = "";
    try { cached = window.localStorage.getItem("fsm_admin_key") || ""; } catch (_) {}
    if (keyInput && cached) keyInput.value = cached;

    const applyPass = (adminKey) => {
        try { window.localStorage.setItem("fsm_admin_key", adminKey); } catch (_) {}
        const panelInput = document.getElementById("admin-key-input");
        if (panelInput) panelInput.value = adminKey;
        if (gate) gate.style.display = "none";
        if (app) app.style.display = "block";
    };

    return new Promise((resolve) => {
        if (!form) {
            // 降级：无表单时直接放行（不应发生）
            if (gate) gate.style.display = "none";
            if (app) app.style.display = "block";
            resolve("");
            return;
        }

        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            const adminKey = keyInput ? keyInput.value.trim() : "";
            if (!adminKey) {
                if (errorEl) { errorEl.textContent = "请输入管理员密钥。"; errorEl.style.display = "block"; }
                return;
            }
            if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = "验证中..."; }
            if (errorEl) errorEl.style.display = "none";

            try {
                const resp = await fetch("/api/v1/spaces/admin/bookings", {
                    headers: { "X-Admin-Key": adminKey },
                });
                if (resp.ok) {
                    applyPass(adminKey);
                    resolve(adminKey);
                } else if (resp.status === 403) {
                    if (errorEl) { errorEl.textContent = "密钥错误，请重试。"; errorEl.style.display = "block"; }
                    if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = "进入管理大盘"; }
                } else {
                    if (errorEl) { errorEl.textContent = "服务暂不可用，请稍后重试。"; errorEl.style.display = "block"; }
                    if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = "进入管理大盘"; }
                }
            } catch (err) {
                console.error("管理员鉴权失败", err);
                if (errorEl) { errorEl.textContent = "网络异常，请检查服务是否正常。"; errorEl.style.display = "block"; }
                if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = "进入管理大盘"; }
            }
        });
    });
}

async function bootstrapFsmDashboard() {
    const adminKey = await verifyAdminAccessBeforeEnter();
    if (!adminKey) {
        return;
    }
    initSpacePanels(adminKey);
    initFsmPanel();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => { bootstrapFsmDashboard(); });
} else {
    bootstrapFsmDashboard();
}
