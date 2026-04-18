// 全局 WebSocket 通信与反馈通道
export class WebSocketManager {
    constructor(url) {
        this.url = url;
        this.socket = null;
    }

    connect() {
        // TODO: 初始化 WebSocket 连接以接收抢票结果回执
        console.log("WebSocket connecting to", this.url);
    }
}
