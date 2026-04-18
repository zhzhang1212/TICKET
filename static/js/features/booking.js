import { WebSocketManager } from "../core/ws.js";

const WS_URL = !!location.hostname ? `ws://${location.host}/api/v1/ws` : null; 
let wsManager = null;
const userId = "User_" + Math.floor(Math.random() * 1000); // 假装一个用户的身份

document.addEventListener("DOMContentLoaded", () => {
    const statusMsg = document.getElementById("status-msg");
    const initBtn = document.getElementById("btn-init");
    const bookBtn = document.getElementById("btn-book");

    // 1. 初始化建立自己身份的长连接
    statusMsg.innerText = `欢迎你: ${userId}`;
    wsManager = new WebSocketManager(`${WS_URL}/${userId}`);
    wsManager.connect(statusMsg);

    // 2. 模拟管理员下发活动
    initBtn.addEventListener("click", async () => {
        try {
            const r = await fetch("/api/v1/events", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({slot_id: "test_slot_1", capacity: 2}) // 设置2个假座位
            });
            const res = await r.json();
            alert(res.message);
        } catch (e) {
            console.error("创建失败", e);
        }
    });

    // 3. 模拟“点击抢票”
    bookBtn.addEventListener("click", async () => {
        bookBtn.disabled = true;
        statusMsg.innerText = "正在进行瞬发网络请求抢占...";
        
        try {
            const r = await fetch("/api/v1/booking", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    user_id: userId,
                    resource_id: "badminton_court_1",
                    slot_id: "test_slot_1"
                })
            });
            const res = await r.json();
            if (r.ok) {
                // 如果 Redis 秒杀阶段没被拦住，代表“排上了队”
                // 然后就在页面上静静等待前面 wsManager 接收后端的确权推送了！
                statusMsg.innerText = res.message; 
                statusMsg.style.color = "blue";
            } else {
                // Redis 发现满载，没票了，拒绝！
                statusMsg.innerText = "❌ 失败: " + res.detail;
                statusMsg.style.color = "red";
            }
        } catch (e) {
            statusMsg.innerText = "❌ 网络错误";
        }
        setTimeout(() => bookBtn.disabled = false, 1000);
    });
});
