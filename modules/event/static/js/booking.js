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
                        const card = document.createElement("div");
                        card.className = "event-card activity-btn";
                        card.dataset.id = ev.slot_id;
                        card.dataset.name = ev.event_name;
                        const bdColor = colors[idx % colors.length];
                        card.style.borderTopColor = bdColor;
                        
                        card.innerHTML = `
                            <div>
                                <h3 style="margin-top:0; color:${bdColor};">🎫 ${ev.event_name || ev.slot_id}</h3>
                                <p style="color:#666; font-size:0.95em;">${ev.description || "暂无描述"}</p>
                            </div>
                            <div style="font-size:0.9em; margin-top:15px; background:#f5f5f5; padding:10px; border-radius:4px; text-align:center;">
                                <span style="display:block; margin-bottom:5px;">有效票数: <strong>${ev.total_capacity}</strong></span>
                                <span>剩余抢夺: <strong style="color:#e91e63; font-size:1.1em;">${ev.remaining_stock}</strong></span>
                            </div>
                        `;
                        
                        card.addEventListener("click", () => {
                            window.location.href = `/event/detail?slot_id=${ev.slot_id}`;
                        });
                        
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
