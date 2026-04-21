import { WebSocketManager } from "/static/js/core/ws.js?t=1";

const userSession = JSON.parse(localStorage.getItem("campus_user"));
if (!userSession) {
    alert("登录过期或未验证身份！");
    window.location.href = "/login";
}

function initBooking() {
    const dynamicEventsContainer = document.getElementById("dynamic-events-container");

    const loadAllEvents = async () => {
        try {
            const r = await fetch("/api/v1/events/");
            if (r.ok) {
                const events = await r.json();
                if (dynamicEventsContainer) {
                    dynamicEventsContainer.innerHTML = "";
                    if (events.length === 0) {
                        dynamicEventsContainer.innerHTML = '<span style="color:#888;">暂无进行中的活动...</span>';
                        return;
                    }
                    const colors = ["#e91e63", "#9c27b0", "#2196f3", "#ff9800", "#009688"];
                    events.forEach((ev, idx) => {
                        const bdColor = colors[idx % colors.length];
                        const nav = () => { window.location.href = `/event/detail?slot_id=${encodeURIComponent(ev.slot_id)}`; };

                        const card = document.createElement("div");
                        card.className = "event-card activity-btn";
                        card.setAttribute("role", "button");
                        card.setAttribute("tabindex", "0");
                        card.style.borderTopColor = bdColor;

                        const h3 = document.createElement("h3");
                        h3.style.cssText = `margin-top:0; color:${bdColor};`;
                        h3.textContent = `🎫 ${ev.event_name || ev.slot_id}`;

                        const p = document.createElement("p");
                        p.style.cssText = "color:#555; font-size:0.95em;";
                        p.textContent = ev.description || "暂无描述";

                        const stats = document.createElement("div");
                        stats.style.cssText = "font-size:0.9em; margin-top:15px; background:#f5f5f5; padding:10px; border-radius:4px; text-align:center;";
                        stats.innerHTML = `<span style="display:block; margin-bottom:5px;">有效票数: <strong>${ev.total_capacity}</strong></span><span>剩余票数: <strong style="color:#e91e63; font-size:1.1em;">${ev.remaining_stock}</strong></span>`;

                        card.appendChild(h3);
                        card.appendChild(p);
                        card.appendChild(stats);
                        card.addEventListener("click", nav);
                        card.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") nav(); });
                        dynamicEventsContainer.appendChild(card);
                    });
                }
            } else {
                if (dynamicEventsContainer) dynamicEventsContainer.innerHTML = '<span style="color:red;">获取活动大厅失败</span>';
            }
        } catch (e) {
            console.error("加载活动列表异常", e);
            if (dynamicEventsContainer) dynamicEventsContainer.innerHTML = '<span style="color:red;">网络请求加载失败...</span>';
        }
    };
    
    // 初始化活动列表
    loadAllEvents();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initBooking);
} else {
    initBooking();
}
