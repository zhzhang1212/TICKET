function initFsmPanel() {
    const btnTicketMgr = document.getElementById("btn-ticket-mgr");
    const detailPanel = document.getElementById("detail-panel");
    const eventSelector = document.getElementById("event-selector");
    const btnRefresh = document.getElementById("btn-refresh");
    const eventDesc = document.getElementById("event-desc");
    const eventStockInfo = document.getElementById("event-stock-info");
    const recordsContainer = document.getElementById("records-container");

    // 点击大盘票务管理卡片展开详情面板
    if(btnTicketMgr){
        btnTicketMgr.addEventListener("click", () => {
            detailPanel.style.display = "block";
        });
    }

    const fetchDetail = async () => {
        const slotId = eventSelector.value;
        if (!slotId) {
            alert("请先选择一个特定的活动！");
            return;
        }

        try {
            const r = await fetch(`/api/v1/events/${slotId}`);
            if (r.ok) {
                const data = await r.json();
                eventDesc.innerText = data.description || "【暂无介绍】";
                eventStockInfo.innerText = `有效票数：${data.total_capacity} | 剩余票数：${data.remaining_stock}`;
                
                recordsContainer.innerHTML = "";
                if (data.successful_bookings && data.successful_bookings.length > 0) {
                    // 对记录按时间排序，确保时间先后顺序
                    const sorted = data.successful_bookings.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
                    
                    sorted.forEach((record, index) => {
                        const li = document.createElement("li");
                        li.className = "record-item";
                        li.innerHTML = `
                            <span><strong>No.${index+1}</strong> 用户: <span style="color:#2196f3">${record.user_id}</span> </strong> 凭证号: <span style="font-size:0.85em;color:#aaa">${record.voucher}</span></span>
                            <span class="timestamp">${record.timestamp}</span>
                        `;
                        recordsContainer.appendChild(li);
                    });
                } else {
                    recordsContainer.innerHTML = '<li class="record-item" style="color: #999;">暂无抢票成功记录...</li>';
                }
            } else {
                eventDesc.innerText = "活动尚未发售或无数据。";
                eventStockInfo.innerText = "--";
                recordsContainer.innerHTML = '<li class="record-item" style="color: #999;">请联系活动运营管理员执行初始化发布发售。</li>';
            }
        } catch (e) {
            console.error(e);
            alert("加载明细异常");
        }
    };

    if(btnRefresh) btnRefresh.addEventListener("click", fetchDetail);
    if(eventSelector) eventSelector.addEventListener("change", fetchDetail);
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initFsmPanel);
} else {
    initFsmPanel();
}