function initSpacePanels() {
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

    const fmtDateTime = (iso) => {
        if (!iso) return "--";
        const d = new Date(iso);
        return d.toLocaleString("zh-CN", { hour12: false }).replace(/\//g, "-");
    };

    const statusClass = (s) => {
        if (!s) return "";
        if (s === "confirmed") return "status-confirmed";
        if (s === "cancelled") return "status-cancelled";
        return "status-pending";
    };

    const statusLabel = (s) => {
        const map = { confirmed: "已确认", cancelled: "已取消", pending: "待确认" };
        return map[s] || s;
    };

    const loadSpaceData = async (container, type) => {
        if (!container) return;
        container.innerHTML = '<p style="color:#888;">正在加载...</p>';
        try {
            const r = await fetch("/api/v1/spaces/admin/bookings");
            if (!r.ok) { container.innerHTML = '<p style="color:red;">加载失败，请重试。</p>'; return; }
            const data = await r.json();
            const rows = type === "academic" ? (data.academic || []) : (data.sports || []);
            if (rows.length === 0) {
                container.innerHTML = '<p class="empty-hint">暂无预约记录。</p>';
                return;
            }
            const wrapper = document.createElement("div");
            wrapper.className = "table-wrapper";
            const table = document.createElement("table");
            table.className = "admin-table";

            if (type === "academic") {
                table.innerHTML = '<thead><tr><th>预约ID</th><th>用户</th><th>场地</th><th>开始时间</th><th>结束时间</th><th>状态</th></tr></thead>';
                const tbody = document.createElement("tbody");
                rows.forEach(row => {
                    const tr = document.createElement("tr");
                    const tdId = document.createElement("td"); tdId.textContent = row.booking_id;
                    const tdUser = document.createElement("td"); tdUser.textContent = row.user_id || "--";
                    const tdSpace = document.createElement("td"); tdSpace.textContent = row.space_name || row.space_id;
                    const tdStart = document.createElement("td"); tdStart.textContent = fmtDateTime(row.actual_start);
                    const tdEnd = document.createElement("td"); tdEnd.textContent = fmtDateTime(row.actual_end);
                    const tdSt = document.createElement("td");
                    tdSt.textContent = statusLabel(row.status);
                    tdSt.className = statusClass(row.status);
                    tr.append(tdId, tdUser, tdSpace, tdStart, tdEnd, tdSt);
                    tbody.appendChild(tr);
                });
                table.appendChild(tbody);
            } else {
                table.innerHTML = '<thead><tr><th>预约ID</th><th>用户</th><th>场地</th><th>日期</th><th>时段</th><th>状态</th></tr></thead>';
                const tbody = document.createElement("tbody");
                rows.forEach(row => {
                    const tr = document.createElement("tr");
                    const tdId = document.createElement("td"); tdId.textContent = (row.group_booking_id || row.booking_ids[0]);
                    const tdUser = document.createElement("td"); tdUser.textContent = row.user_id || "--";
                    const tdSpace = document.createElement("td"); tdSpace.textContent = row.space_ids.join(", ");
                    const tdDate = document.createElement("td"); tdDate.textContent = row.slot_date;
                    const tdHour = document.createElement("td"); tdHour.textContent = `${row.slot_hour}:00`;
                    const tdSt = document.createElement("td");
                    tdSt.textContent = statusLabel(row.status);
                    tdSt.className = statusClass(row.status);
                    tr.append(tdId, tdUser, tdSpace, tdDate, tdHour, tdSt);
                    tbody.appendChild(tr);
                });
                table.appendChild(tbody);
            }
            wrapper.appendChild(table);
            container.innerHTML = "";
            container.appendChild(wrapper);
        } catch (e) {
            console.error("加载空间预约数据失败", e);
            container.innerHTML = '<p style="color:red;">网络异常，无法加载数据。</p>';
        }
    };

    if (btnRoomMgr) {
        const open = () => { showSection(roomSection); loadSpaceData(roomContainer, "academic"); };
        btnRoomMgr.onclick = open;
        btnRoomMgr.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") open(); });
    }
    if (btnVenueMgr) {
        const open = () => { showSection(venueSection); loadSpaceData(venueContainer, "sports"); };
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
                    headers: {"Content-Type": "application/json"},
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
                    alert("发布成功！");
                    if (detailPanel) detailPanel.style.display = "none";
                    if (listContainer) listContainer.style.display = "grid";
                    loadEvents();
                } else {
                    const err = await r.json();
                    alert("发布失败：" + JSON.stringify(err));
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
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify(payload)
                });
                if (r.ok) {
                    alert("更改保存成功！");
                    if (detailPanel) detailPanel.style.display = "none";
                    if (listContainer) listContainer.style.display = "grid";
                    loadEvents();
                } else {
                    const err = await r.json();
                    alert("更新失败: " + JSON.stringify(err));
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

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => { initSpacePanels(); initFsmPanel(); });
} else {
    initSpacePanels();
    initFsmPanel();
}
