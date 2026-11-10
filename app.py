"""
app.py — Flask + SocketIO 主应用
配置从 config.json 读取，支持页面内热重载
"""

import os
import json
import threading
import time
from flask import Flask, render_template, jsonify, request, Response
from flask_socketio import SocketIO, emit
from obd_client import create_obd_client

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

# ── 配置读写 ───────────────────────────────────────────────────────────────────
def load_config() -> dict:
    defaults = {"simulate": True, "obd_port": "192.168.0.10:35000",
                "car_model": "han_ev", "poll_interval": 1.0}
    try:
        with open(CONFIG_FILE, "r") as f:
            cfg = json.load(f)
        defaults.update(cfg)
    except Exception:
        pass
    return defaults

def save_config(cfg: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

# ── 应用初始化 ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = "obd-secret-2024"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

cfg = load_config()
obd_client = create_obd_client(simulate=cfg["simulate"],
                                port=cfg["obd_port"],
                                car_model=cfg["car_model"])

history_lock = threading.Lock()
history = []
MAX_HISTORY = 100
_poll_running = True

# ── 后台轮询 ───────────────────────────────────────────────────────────────────
def poll_loop():
    global _poll_running
    while True:
        if _poll_running:
            try:
                data = obd_client.read_all()
                with history_lock:
                    history.append({
                        "timestamp":    data["timestamp"],
                        "soc":          data.get("soc"),
                        "speed":        data.get("speed"),
                        "power_kw":     data.get("power_kw"),
                        "batt_voltage": data.get("batt_voltage"),
                        "batt_current": data.get("batt_current"),
                    })
                    if len(history) > MAX_HISTORY:
                        history.pop(0)
                socketio.emit("obd_data", data)
            except Exception as e:
                print(f"[poll] 读取异常: {e}")
        time.sleep(load_config().get("poll_interval", 1.0))

# ── 路由 ───────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/data")
def api_data():
    return jsonify(obd_client.read_all())

@app.route("/api/dtc")
def api_dtc():
    codes = obd_client.get_dtc()
    return jsonify({"codes": codes, "count": len(codes)})

@app.route("/api/dtc/clear", methods=["POST"])
def api_dtc_clear():
    ok = obd_client.clear_dtc()
    return jsonify({"success": ok, "message": "故障码已清除" if ok else "清除失败"})

@app.route("/api/scan")
def api_scan():
    return jsonify(obd_client.scan_all_systems())

@app.route("/api/cells")
def api_cells():
    return jsonify(obd_client.get_cell_data())

@app.route("/api/stats")
def api_stats():
    return jsonify(obd_client.get_stats())

@app.route("/api/history")
def api_history():
    with history_lock:
        return jsonify(list(history))

@app.route("/api/inject_fault", methods=["POST"])
def api_inject_fault():
    code = request.json.get("code", "P0A80")
    if hasattr(obd_client, "inject_fault"):
        obd_client.inject_fault(code)
        return jsonify({"success": True, "injected": code})
    return jsonify({"success": False, "message": "仅模拟模式支持"})

@app.route("/api/export")
def api_export():
    with history_lock:
        rows = list(history)
    lines = ["时间,SOC%,车速km/h,功率kW,电压V,电流A"]
    for r in rows:
        lines.append(f"{r.get('timestamp','')},{r.get('soc','')},{r.get('speed','')}"
                     f",{r.get('power_kw','')},{r.get('batt_voltage','')},{r.get('batt_current','')}")
    return Response("\n".join(lines), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment;filename=obd_data.csv"})

# ── EQ1 PID扫描接口 ────────────────────────────────────────────────────────────
_scan_thread = None

@app.route("/api/eq1/can/listen")
def api_eq1_can_listen():
    """触发EQ1 CAN监听，返回单体电压数据"""
    from obd_client import get_eq1_scanner
    cfg = load_config()
    scanner = get_eq1_scanner(port=cfg["obd_port"])
    duration = int(request.args.get("duration", 10))
    result = scanner.listen_can(duration=duration)
    return jsonify(result)

@app.route("/api/eq1/scan/start", methods=["POST"])
def api_eq1_scan_start():
    global _scan_thread
    from obd_client import get_eq1_scanner
    cfg = load_config()
    scanner = get_eq1_scanner(port=cfg["obd_port"])
    if scanner.get_progress()["running"]:
        return jsonify({"success": False, "message": "扫描已在进行中"})
    def run():
        scanner.scan()
    _scan_thread = threading.Thread(target=run, daemon=True)
    _scan_thread.start()
    return jsonify({"success": True, "message": "PID扫描已启动，预计需要5~15分钟"})

@app.route("/api/eq1/scan/stop", methods=["POST"])
def api_eq1_scan_stop():
    from obd_client import _eq1_scanner
    if _eq1_scanner:
        _eq1_scanner.stop()
    return jsonify({"success": True})

@app.route("/api/eq1/scan/progress")
def api_eq1_scan_progress():
    from obd_client import _eq1_scanner
    if not _eq1_scanner:
        return jsonify({"running": False, "pct": 0, "found": 0, "total": 0})
    return jsonify(_eq1_scanner.get_progress())

@app.route("/api/eq1/scan/results")
def api_eq1_scan_results():
    import os, json
    path = os.path.join(os.path.dirname(__file__), "eq1_pids.json")
    if not os.path.exists(path):
        return jsonify({})
    with open(path) as f:
        return jsonify(json.load(f))

@app.route("/api/eq1/analyze")
def api_eq1_analyze():
    from obd_client import get_eq1_scanner
    cfg = load_config()
    scanner = get_eq1_scanner(port=cfg["obd_port"])
    return jsonify(scanner.analyze())

@app.route("/api/eq1/confirm", methods=["POST"])
def api_eq1_confirm():
    """保存用户确认的PID配置"""
    from obd_client import get_eq1_scanner
    cfg = load_config()
    scanner = get_eq1_scanner(port=cfg["obd_port"])
    confirmed = request.json  # {"SOC":"0x1001","total_voltage":"0x1003",...}
    path = scanner.save_confirmed_config(confirmed)
    return jsonify({"success": True, "message": f"EQ1配置已保存", "path": path})

@app.route("/api/eq1/report")
def api_eq1_report():
    """下载完整分析报告（供人工/AI分析）"""
    import os
    from obd_client import get_eq1_scanner
    cfg = load_config()
    scanner = get_eq1_scanner(port=cfg["obd_port"])
    report = scanner.export_report()
    return Response(report, mimetype="text/plain; charset=utf-8",
                    headers={"Content-Disposition": "attachment;filename=eq1_report.txt"})

# ── 配置接口 ───────────────────────────────────────────────────────────────────
@app.route("/api/config", methods=["GET"])
def api_config_get():
    return jsonify(load_config())

@app.route("/api/config", methods=["POST"])
def api_config_save():
    global obd_client, history
    new_cfg = request.json
    # 合并并保存
    cfg = load_config()
    cfg.update(new_cfg)
    save_config(cfg)
    # 重建OBD客户端
    try:
        if hasattr(obd_client, "disconnect"):
            obd_client.disconnect()
    except Exception:
        pass
    obd_client = create_obd_client(simulate=cfg["simulate"],
                                    port=cfg["obd_port"],
                                    car_model=cfg["car_model"])
    # 清空历史
    with history_lock:
        history.clear()
    socketio.emit("config_changed", cfg)
    return jsonify({"success": True, "config": cfg,
                    "message": f"已切换到{'模拟' if cfg['simulate'] else '真实'}模式"
                               f"，车型：{cfg['car_model']}"})

# ── SocketIO ───────────────────────────────────────────────────────────────────
@socketio.on("connect")
def on_connect():
    print(f"[ws] 连接: {request.sid}")
    emit("obd_data", obd_client.read_all())
    emit("config_changed", load_config())

@socketio.on("disconnect")
def on_disconnect():
    print(f"[ws] 断开: {request.sid}")

# ── 启动 ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    t = threading.Thread(target=poll_loop, daemon=True)
    t.start()
    cfg = load_config()
    print("=" * 50)
    print("  新能源OBD检测系统已启动")
    print(f"  模式: {'模拟' if cfg['simulate'] else '真实ELM327'}")
    print(f"  车型: {cfg['car_model']}")
    print("  浏览器访问: http://0.0.0.0:5000")
    print("=" * 50)
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)
