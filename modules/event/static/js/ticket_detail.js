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

const urlParams = new URLSearchParams(window.location.search);
let currentOrderId = urlParams.get('order_id') || "";
let countdownTimer = null;
let currentSlotId = "";

function initTicketDetail() {
    if (!currentOrderId) {
        alert("未指定订单ID");
        window.location.href = "/";
        return;
    }

    const tEventName = document.getElementById("t-event-name");
    const tUsername = document.getElementById("t-username");
    const tTimestamp = document.getElementById("t-timestamp");
    const tOrderId = document.getElementById("t-order-id");
    const tVoucherRow = document.getElementById("t-voucher-row");
    const tVoucher = document.getElementById("t-voucher");
    const tStatus = document.getElementById("t-status");
    
    const actionZone = document.getElementById("action-zone");
    const payCountdownZone = document.getElementById("pay-countdown-zone");
    const payCountdown = document.getElementById("pay-countdown");
    const btnPay = document.getElementById("btn-pay");
    const btnCancel = document.getElementById("btn-cancel");
    
    const loadingMsg = document.getElementById("loading-msg");
    const ticketInfo = document.getElementById("ticket-info");
    const systemMsg = document.getElementById("system-msg");

    const fetchTicket = async () => {
        try {
            const r = await fetch(`/api/v1/events/ticket/${userId}/${currentOrderId}`);
            if (r.ok) {
                const data = await r.json();
                
                loadingMsg.style.display = "none";
                ticketInfo.style.display = "block";
                
                tEventName.innerText = data.event_name || "--";
                tUsername.innerText = username;
                tTimestamp.innerText = data.timestamp || "--";
                tOrderId.innerText = data.order_id || currentOrderId;
                currentSlotId = data.slot_id;
                
                const statusStr = data.status || "";
                tStatus.innerText = statusStr;
                
                // Color badges
                if (statusStr.includes("成功") || statusStr.includes("已支付")) {
                    tStatus.style.background = "#4caf50";
                } else if (statusStr.includes("失败") || statusStr.includes("取消") || statusStr.includes("关闭")) {
                    tStatus.style.background = "#f44336";
                } else if (statusStr.includes("待支付")) {
                    tStatus.style.background = "#ff9800";
                } else {
                    tStatus.style.background = "#2196f3";
                }
                
                if (data.voucher) {
                    tVoucherRow.style.display = "block";
                    tVoucher.innerText = data.voucher;
                } else {
                    tVoucherRow.style.display = "none";
                    tVoucher.innerText = "--";
                }

                // Control buttons
                btnPay.style.display = "none";
                btnCancel.style.display = "none";
                payCountdownZone.style.display = "none";
                
                if (statusStr === "待支付 (请在5分钟内完成)") {
                    btnPay.style.display = "inline-block";
                    btnCancel.style.display = "inline-block";
                    payCountdownZone.style.display = "block";
                    
                    if (data.timestamp) {
                        const createTime = new Date(data.timestamp).getTime();
                        const now = new Date().getTime();
                        const passSec = Math.floor((now - createTime)/1000);
                        if (passSec < 300) {
                            startCountdown(300 - passSec);
                        } else {
                            if (countdownTimer) clearInterval(countdownTimer);
                            payCountdown.innerText = "已超时";
                            btnPay.disabled = true;
                        }
                    } else {
                        startCountdown(300);
                    }
                } else if (statusStr === "失败 (已售罄)" || statusStr === "失败 (已关闭)") {
                    // Maybe show cancel if needed? Usually closed means no action.
                    if (countdownTimer) clearInterval(countdownTimer);
                } else if (statusStr.includes("落库") || statusStr.includes("库")) {
                    if (countdownTimer) clearInterval(countdownTimer);
                }
            } else {
                loadingMsg.innerHTML = "🚨 加载订单记录失败，找不到该笔订单。";
                loadingMsg.style.color = "red";
            }
        } catch(e) {
            console.error("加载订单详情异常", e);
            loadingMsg.innerHTML = "🚨 网络异常，无法加载。";
            loadingMsg.style.color = "red";
        }
    };

    fetchTicket();

    // Setup websocket to get real-time updates
    systemMsg.innerText = `用户 ${username}`;
    wsManager = new WebSocketManager(`${WS_URL}/${userId}`);
    wsManager.connect(systemMsg);

    const oldOnMessage = wsManager.socket.onmessage;
    wsManager.socket.onmessage = (event) => {
        if (oldOnMessage) oldOnMessage(event);
        const data = JSON.parse(event.data);
        if (data.status === "success" || data.status === "timeout") {
            // refresh data
            setTimeout(() => {
                fetchTicket();
            }, 500);
        }
    };

    function startCountdown(duration) {
        let Math = window.Math;
        let timeLeft = duration;
        
        const m0 = Math.floor(timeLeft / 60).toString().padStart(2, '0');
        const s0 = (timeLeft % 60).toString().padStart(2, '0');
        payCountdown.innerText = `${m0}:${s0}`;
        
        if (countdownTimer) clearInterval(countdownTimer);
        
        countdownTimer = setInterval(() => {
            if (timeLeft <= 0) {
                clearInterval(countdownTimer);
                fetchTicket(); // refresh
                return;
            }
            timeLeft--;
            const m = Math.floor(timeLeft / 60).toString().padStart(2, '0');
            const s = (timeLeft % 60).toString().padStart(2, '0');
            payCountdown.innerText = `${m}:${s}`;
        }, 1000);
    }

    btnPay.addEventListener("click", async () => {
        btnPay.disabled = true;
        btnCancel.disabled = true;
        systemMsg.innerText = "正在支付中...";
        try {
            const r = await fetch("/api/v1/events/pay", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    user_id: userId,
                    slot_id: currentSlotId,
                    order_id: currentOrderId
                })
            });
            const res = await r.json();
            if (r.ok) {
                if (countdownTimer) clearInterval(countdownTimer);
                systemMsg.innerText = "✅ 支付成功！正等待落库队列最终出票。";
                systemMsg.style.color = "green";
                fetchTicket();
            } else {
                systemMsg.innerText = "❌ 支付异常: " + (res.detail || "");
                systemMsg.style.color = "red";
                btnPay.disabled = false;
                btnCancel.disabled = false;
            }
        } catch (e) {
            systemMsg.innerText = "❌ 支付网络错误";
            btnPay.disabled = false;
            btnCancel.disabled = false;
        }
    });

    btnCancel.addEventListener("click", async () => {
        btnCancel.disabled = true;
        btnPay.disabled = true;
        systemMsg.innerText = "正在取消订单...";
        try {
            const r = await fetch("/api/v1/events/cancel", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    user_id: userId,
                    slot_id: currentSlotId,
                    order_id: currentOrderId
                })
            });
            const res = await r.json();
            if (r.ok) {
                if (countdownTimer) clearInterval(countdownTimer);
                systemMsg.innerText = "🚫 订单已手动取消，未扣除信誉分。";
                systemMsg.style.color = "#666";
                fetchTicket();
            } else {
                systemMsg.innerText = "❌ 取消异常: " + (res.detail || "");
                systemMsg.style.color = "red";
                btnCancel.disabled = false;
                btnPay.disabled = false;
            }
        } catch (e) {
            systemMsg.innerText = "❌ 取消网络错误";
            btnCancel.disabled = false;
            btnPay.disabled = false;
        }
    });

}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initTicketDetail);
} else {
    initTicketDetail();
}