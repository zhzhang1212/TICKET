export class WebSocketManager {
    constructor(url) {
        this.url = url;
        this.socket = null;
    }

    connect(statusMsgEl) {
        if (!this.url) return;
        this.socket = new WebSocket(this.url);
        
        this.socket.onopen = () => console.log("WebSocket 已连接");
        
        // 核心：监听 Redis -> 后端 -> WebSocekt 的最终落库成功信号
        this.socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.status === "success") {
                statusMsgEl.innerText = "✅ " + data.msg;
                statusMsgEl.style.color = "green";
                
                // 收到后端确权通知后，自动刷新主页的档案列表，获取最新的状态数据
                if (typeof window.fetchProfile === "function") {
                    const userStr = localStorage.getItem("campus_user");
                    if (userStr) {
                        const user = JSON.parse(userStr);
                        window.fetchProfile(user.userId || user.id);
                    }
                }
            }
        };
        
        this.socket.onclose = () => {
            console.log("WebSocket 连接已断开，尝试重连...");
            setTimeout(() => this.connect(statusMsgEl), 3000);
        };
    }
}
