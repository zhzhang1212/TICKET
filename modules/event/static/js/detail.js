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
let globalTimer = null;
function setupActivityClock(info) {
    if (globalTimer) clearInterval(globalTimer);
    const bookBtn = document.getElementById("btn-book");
    const timingInfo = document.getElementById("timing-info");
    const penaltyInfo = document.getElementById("penalty-info");
    
    let penaltyRemaining = info.cancel_penalty_remain_sec || 0;
    let startTimeStr = info.start_time || null;
    let endTimeStr = info.end_time || null;
    
    globalTimer = setInterval(() => {
        let isBookable = true;
        let now = new Date();
        
        let startMsg = "";
        let endMsg = "";
        
        if (startTimeStr) {
            let startT = new Date(startTimeStr + "Z");
            if (isNaN(startT.getTime())) startT = new Date(startTimeStr);
            let diffSec = Math.floor((startT - now) / 1000);
            if (diffSec > 0) {
                isBookable = false;
                startMsg = "距离预订开放还有 " + formatSec(diffSec);
            }
        }
        if (endTimeStr) {
            let endT = new Date(endTimeStr + "Z");
            if (isNaN(endT.getTime())) endT = new Date(endTimeStr);
            let diffSec = Math.floor((endT - now) / 1000);
            if (diffSec <= 0) {
                isBookable = false;
                startMsg = "预订已经结束！";
            } else if(isBookable) {
                startMsg = "距离预订截止还剩 " + formatSec(diffSec);
            }
        }
        
        timingInfo.innerText = startMsg;
        
        if (penaltyRemaining > 0) {
            isBookable = false;
            penaltyInfo.innerText = "刚刚取消，需等待 " + formatSec(penaltyRemaining) + " 后重试";
            penaltyRemaining--;
        } else {
            penaltyInfo.innerText = "";
        }
        
        if (isBookable && info.remaining_stock > 0) {
            bookBtn.disabled = false;
            bookBtn.style.background = "#ff9800";
            bookBtn.innerText = "点击报名/抢票";
        } else {
            bookBtn.disabled = true;
            bookBtn.style.background = "#9e9e9e";
            if (info.remaining_stock <= 0) {
                bookBtn.innerText = "已售罄";
            }
        }
    }, 1000);
}

function formatSec(sec) {
    const mins = Math.floor(sec / 60).toString().padStart(2, '0');
    const secs = (sec % 60).toString().padStart(2, '0');
    return mins + ":" + secs;
}


const urlParams = new URLSearchParams(window.location.search);
let currentEventId = urlParams.get('slot_id') || "";
let currentEventName = currentEventId;
let currentOrderId = "";
let countdownTimer = null;

function initDetail() {
    const statusMsg = document.getElementById("status-msg");
    const bookBtn = document.getElementById("btn-book");
    const detailTitle = document.getElementById("detail-title");
    
    const eventDesc = document.getElementById("event-desc");
    const eventTotal = document.getElementById("event-total");
    const eventStock = document.getElementById("event-stock");
    
    // Add payment zone dynamically
    const paymentZone = document.createElement("div");
    paymentZone.id = "payment-zone";
    paymentZone.style.display = "none";
    paymentZone.style.marginTop = "20px";
    paymentZone.style.padding = "15px";
    paymentZone.style.border = "1px solid #ff9800";
    paymentZone.style.borderRadius = "8px";
    paymentZone.style.backgroundColor = "#fff3e0";
    paymentZone.innerHTML = `
        <h3 style="color:#e65100; margin-top:0;">💳 待支付订单</h3>
        <p>订单流水号：<strong id="pay-order-id"></strong></p>
        <p style="color:red; font-weight:bold;">剩余支付时间：<span id="pay-countdown">05:00</span></p>
        <div style="margin-top: 15px;">
            <button id="btn-pay" style="background:#4caf50; color:white; margin-right:10px;">立即模拟支付</button>
            <button id="btn-cancel" style="background:#f44336; color:white;">取消订单</button>
        </div>
    `;
    bookBtn.parentNode.parentNode.appendChild(paymentZone);

    const btnPay = document.getElementById("btn-pay");
    const btnCancel = document.getElementById("btn-cancel");
    const payCountdown = document.getElementById("pay-countdown");
    const payOrderId = document.getElementById("pay-order-id");

    const fetchEventDetail = async (slotId) => {
        try {
            const r = await fetch(`/api/v1/events/${slotId}`);
            if (r.ok) {
                const data = await r.json();
                currentEventName = data.event_name || slotId;
                detailTitle.innerText = `🎫 ${currentEventName}`;
                eventDesc.innerText = data.description || "无描述信息。";
                eventTotal.innerText = data.total_capacity;
                eventStock.innerText = data.remaining_stock;
            } else {
                detailTitle.innerText = "活动详情";
                eventDesc.innerText = "🚨 尚未由管理员发布或获取失败";
                eventTotal.innerText = "--";
                eventStock.innerText = "--";
            }
        } catch(e) {
            console.error("加载活动详情异常", e);
        }
    };

    if (!currentEventId) {
        alert("未指定活动ID");
        window.location.href = "/event";
        return;
    }

    fetchEventDetail(currentEventId);

    statusMsg.innerText = `用户 ${username}`;
    wsManager = new WebSocketManager(`${WS_URL}/${userId}`);
    wsManager.connect(statusMsg);

    const oldOnMessage = wsManager.socket.onmessage;
    wsManager.socket.onmessage = (event) => {
        if (oldOnMessage) oldOnMessage(event);
        const data = JSON.parse(event.data);
        if ((data.status === "success" || data.status === "timeout") && currentEventId) {
            setTimeout(() => {
                fetchEventDetail(currentEventId);
            }, 500);
            
            if (data.status === "timeout") {
                paymentZone.style.display = "none";
                bookBtn.style.display = "inline-block";
                bookBtn.disabled = false;
                if (countdownTimer) clearInterval(countdownTimer);
            }
        }
    };

    function startCountdown() {
        let timeLeft = 300; // 5 minutes
        payCountdown.innerText = "05:00";
        if (countdownTimer) clearInterval(countdownTimer);
        
        countdownTimer = setInterval(() => {
            timeLeft--;
            let m = Math.floor(timeLeft / 60).toString().padStart(2, '0');
            let s = (timeLeft % 60).toString().padStart(2, '0');
            payCountdown.innerText = `${m}:${s}`;
            if (timeLeft <= 0) {
                clearInterval(countdownTimer);
            }
        }, 1000);
    }

    bookBtn.addEventListener("click", async () => {
        if (!currentEventId) return;
        bookBtn.disabled = true;
        statusMsg.innerText = "正在进行规则校验与预扣库存...";
        statusMsg.style.color = "#666";
        
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
                currentOrderId = res.order_id;
                
                // Show payment zone
                bookBtn.style.display = "none";
                paymentZone.style.display = "block";
                payOrderId.innerText = currentOrderId;
                startCountdown();
            } else {
                const errorStr = typeof res.detail === "string" ? res.detail : JSON.stringify(res.detail);
                statusMsg.innerText = "❌ 失败: " + errorStr;
                statusMsg.style.color = "red";
                setTimeout(() => bookBtn.disabled = false, 1000);
            }
        } catch (e) {
            statusMsg.innerText = "❌ 网络错误";
            statusMsg.style.color = "red";
            setTimeout(() => bookBtn.disabled = false, 1000);
        }
    });

    btnPay.addEventListener("click", async () => {
        btnPay.disabled = true;
        btnCancel.disabled = true;
        statusMsg.innerText = "正在支付中...";
        try {
            const r = await fetch("/api/v1/events/pay", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    user_id: userId,
                    slot_id: currentEventId,
                    order_id: currentOrderId
                })
            });
            const res = await r.json();
            if (r.ok) {
                if (countdownTimer) clearInterval(countdownTimer);
                paymentZone.style.display = "none";
                statusMsg.innerText = "✅ 支付成功！正等待落库队列最终出票，即将跳转至凭证详情页...";
                statusMsg.style.color = "green";
                setTimeout(() => {
                    window.location.href = `/event/ticket?order_id=${currentOrderId}`;
                }, 1500);
            } else {
                statusMsg.innerText = "❌ 支付异常: " + (res.detail || "");
                statusMsg.style.color = "red";
                btnPay.disabled = false;
                btnCancel.disabled = false;
            }
        } catch (e) {
            statusMsg.innerText = "❌ 支付网络错误";
            btnPay.disabled = false;
            btnCancel.disabled = false;
        }
    });

    btnCancel.addEventListener("click", async () => {
        btnCancel.disabled = true;
        btnPay.disabled = true;
        statusMsg.innerText = "正在取消订单...";
        try {
            const r = await fetch("/api/v1/events/cancel", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    user_id: userId,
                    slot_id: currentEventId,
                    order_id: currentOrderId
                })
            });
            const res = await r.json();
            if (r.ok) {
                if (countdownTimer) clearInterval(countdownTimer);
                paymentZone.style.display = "none";
                bookBtn.style.display = "inline-block";
                bookBtn.disabled = false;
                statusMsg.innerText = "订单已手动取消";
                statusMsg.style.color = "#666";
                fetchEventDetail(currentEventId); // Refresh stock immediately
            } else {
                statusMsg.innerText = "❌ 取消异常: " + (res.detail || "");
                statusMsg.style.color = "red";
                btnCancel.disabled = false;
                btnPay.disabled = false;
            }
        } catch (e) {
            statusMsg.innerText = "❌ 取消网络错误";
            btnCancel.disabled = false;
            btnPay.disabled = false;
        }
    });

}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initDetail);
} else {
    initDetail();
}
