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
                statusMsgEl.innerText = "✅ 后端入库排队完成：" + data.msg;
                statusMsgEl.style.color = "green";
                
                // 生成功二维码特效等
                const code = document.createElement("div");
                code.className = "qr-mock";
                code.innerText = "【凭证号：" + Math.random().toString(36).substring(7) + "】";
                statusMsgEl.appendChild(code);
            }
        };
        
        this.socket.onclose = () => {
            console.log("WebSocket 连接已断开，尝试重连...");
            setTimeout(() => this.connect(statusMsgEl), 3000);
        };
    }
}
