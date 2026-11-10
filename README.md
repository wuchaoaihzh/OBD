# 新能源OBD检测模块

手机/电脑浏览器实时查看车辆数据，支持 ELM327 WiFi 适配器。

## 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 模拟模式（无硬件，直接测试）
python app.py

# 3. 连接真实ELM327 WiFi适配器
OBD_SIMULATE=false OBD_PORT=192.168.0.10:35000 python app.py
```

手机和电脑连接同一局域网后，手机浏览器访问：
`http://<电脑IP>:5000`

## 功能

- 电池 SOC（剩余电量）/ SOH（健康度）仪表盘
- 实时车速、功率、电机温度、电池温度
- 电池电压 / 电流 / 充电状态进度条
- 故障码 DTC 读取与一键清除
- SOC & 车速历史趋势折线图
- WebSocket 实时推送，1秒刷新

## 目录结构

```
obd_monitor/
├── app.py           # Flask + SocketIO 主应用
├── obd_client.py    # OBD连接层（模拟/真实两套）
├── requirements.txt
└── templates/
    └── index.html   # 手机友好的Web界面
```

## ELM327 WiFi 接法

1. 将 ELM327 WiFi 插入车辆 OBD-II 接口（一般在方向盘左下方）
2. 手机/电脑连接 ELM327 发出的 WiFi 热点
3. 默认 IP `192.168.0.10`，端口 `35000`
4. 启动 app.py 即可

## 新能源私有PID扩展

编辑 `obd_client.py` 中 `CUSTOM_PIDS` 字典，添加你车型的 Mode 22 私有PID，
然后在 `RealOBD.read_all()` 里调用即可读取 SOH、BMS 温度等厂商数据。

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| OBD_SIMULATE | true | false 时连接真实ELM327 |
| OBD_PORT | 192.168.0.10:35000 | ELM327地址（WiFi）或串口路径 |
