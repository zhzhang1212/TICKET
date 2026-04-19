import { WebSocketManager } from "/static/js/core/ws.js?t=1";

const WS_URL = !!location.hostname ? `ws://${location.host}/api/v1/ws` : null; 
let wsManager = null;

const userSession = JSON.parse(localStorage.getItem("campus_user"));
if (!userSession) {
    alert("登录过期或未验证身份！");
    window.location.href = "/login";
}
const userId = userSession.userId;
const username = userSession.username;

let currentEventId = "";
let currentEventName = "";

function initBooking() {
    const statusMsg = document.getElementById("status-msg");
    const initBtn = document.getElementById("btn-init");
    const bookBtn = document.getElementById("btn-book");
    const detailPanel = document.getElementById("activity-detail");
    const detailTitle = document.getElementById("detail-title");

    statusMsg.innerText = `👋 欢迎你: ${username} (${userId})`;
    wsManager = new WebSocketManager(`${WS_URL}/${userId}`);
    wsManager.connect(statusMsg);

    document.querySelectorAll(".activity-btn").forEach(btn => {
        btn.addEventListener("click", (e) => {
            currentEventId = e.target.dataset.id;
            currentEventName = e.target.dataset.name;
            detailTitle.innerText = `🎫 ${currentEventName}`;
            detailPanel.style.display = "block";
            statusMsg.innerText = "";
        });
    });

    initBtn.addEventListener("click", async () => {
        if (!currentEventId) return;
        try {
            const r = await fetch("/api/v1/events", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({slot_id: currentEventId, capacity: 2})
            });
            const res = await r.json();
            alert(res.message);
        } catch (e) {
            console.error("创建失败", e);
        }
    });

    bookBtn.addEventListener("click", async () => {
        if (!currentEventId) return;
        bookBtn.disabled = true;
        statusMsg.innerText = "正在进行瞬发网络请求抢占...";
        
        try {
            const r = await fetch("/api/v1/events/seckill", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    user_id: userId,
                    resource_id: currentEventName,
                    slot_id: currentEventId
                })
            });
            const res = await r.json();
            if (r.ok) {
                statusMsg.innerText = res.message; 
                statusMsg.style.color = "blue";
            } else {
                const errorStr = typeof res.detail === "string" ? res.detail : JSON.stringify(res.detail);
                statusMsg.innerText = "❌ 失败: " + errorStr;
                statusMsg.style.color = "red";
            }
        } catch (e) {
            statusMsg.innerText = "❌ 网络错误";
        }
        setTimeout(() => bookBtn.disabled = false, 1000);
    });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initBooking);
} else {
    initBooking();
}
