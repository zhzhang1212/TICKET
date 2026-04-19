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
    
    // New DOM elements
    const eventDesc = document.getElementById("event-desc");
    const eventTotal = document.getElementById("event-total");
    const eventStock = document.getElementById("event-stock");

    const fetchEventDetail = async (slotId) => {
        try {
            const r = await fetch(`/api/v1/events/${slotId}`);
            if (r.ok) {
                const data = await r.json();
                eventDesc.innerText = data.description || "无描述信息。";
                eventTotal.innerText = data.total_capacity;
                eventStock.innerText = data.remaining_stock;
            } else {
                eventDesc.innerText = "🚨 尚未由管理员发布或获取失败";
                eventTotal.innerText = "--";
                eventStock.innerText = "--";
            }
        } catch(e) {
            console.error("加载活动详情异常", e);
        }
    };

    statusMsg.innerText = `👋 欢迎你: ${username} (${userId})`;
    wsManager = new WebSocketManager(`${WS_URL}/${userId}`);
    wsManager.connect(statusMsg);

    // Patch wsManager callback setup to refresh detailed list if matching event
    const oldOnMessage = wsManager.socket.onmessage;
    wsManager.socket.onmessage = (event) => {
        if (oldOnMessage) oldOnMessage(event);
        const data = JSON.parse(event.data);
        if (data.status === "success" && currentEventId) {
            // refresh details half a second after worker clears to let redis persist properly
            setTimeout(() => {
                fetchEventDetail(currentEventId);
            }, 500);
        }
    };

    document.querySelectorAll(".activity-btn").forEach(btn => {
        btn.addEventListener("click", async (e) => {
            currentEventId = e.target.dataset.id;
            currentEventName = e.target.dataset.name;
            detailTitle.innerText = `🎫 ${currentEventName}`;
            detailPanel.style.display = "block";
            statusMsg.innerText = "";
            await fetchEventDetail(currentEventId);
        });
    });

    initBtn.addEventListener("click", async () => {
        if (!currentEventId) return;
        try {
            const descDict = {
                "concert_2026": "某明星的2026春季校园巡演专场，超级火热不容错过！",
                "singing_contest": "校级年度十佳歌手争霸赛巅峰之战决赛门票！"
            };
            const postData = {
                event_name: currentEventName,
                description: descDict[currentEventId] || "精彩活动即将开始！",
                slot_id: currentEventId,
                capacity: 3
            };
            
            const r = await fetch("/api/v1/events", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(postData)
            });
            const res = await r.json();
            alert(res.message);
            await fetchEventDetail(currentEventId); // Auto refresh
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
