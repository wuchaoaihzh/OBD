"""
app.py — Flask + SocketIO 主应用
"""

import os
import threading
import time
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from obd_client import create_obd_client

SIMULATE      = os.environ.get("OBD_SIMULATE", "true").lower() != "false"
OBD_PORT      = os.environ.get("OBD_PORT", "192.168.0.10:35000")
POLL_INTERVAL = 1.0

app      = Flask(__name__)
app.config["SECRET_KEY"] = "obd-secret-2024"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

obd_client = create_obd_client(simulate=SIMULATE, port=OBD_PORT)

history_lock = threading.Lock()
history = []
MAX_HISTORY = 100


def poll_loop():
    while True:
        try:
            data = obd_client.read_all()
            with history_lock:
                history.append({
                    "timestamp": data["timestamp"],
                    "soc":       data.get("soc"),
                    "speed":     data.get("speed"),
                    "power_kw":  data.get("power_kw"),
                    "batt_voltage": data.get("batt_voltage"),
                    "batt_current": data.get("batt_current"),
                })
                if len(history) > MAX_HISTORY:
                    history.pop(0)
            socketio.emit("obd_data", data)
        except Exception as e:
            print(f"[poll] 读取异常: {e}")
        time.sleep(POLL_INTERVAL)


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
    result = obd_client.scan_all_systems()
    return jsonify(result)

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
    """导出历史数据为CSV"""
    with history_lock:
        rows = list(history)
    lines = ["时间,SOC%,车速km/h,功率kW,电压V,电流A"]
    for r in rows:
        lines.append(f"{r.get('timestamp','')},{r.get('soc','')},{r.get('speed','')},{r.get('power_kw','')},{r.get('batt_voltage','')},{r.get('batt_current','')}")
    csv = "\n".join(lines)
    from flask import Response
    return Response(csv, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment;filename=obd_data.csv"})


@socketio.on("connect")
def on_connect():
    print(f"[ws] 连接: {request.sid}")
    emit("obd_data", obd_client.read_all())

@socketio.on("disconnect")
def on_disconnect():
    print(f"[ws] 断开: {request.sid}")


if __name__ == "__main__":
    t = threading.Thread(target=poll_loop, daemon=True)
    t.start()
    print("=" * 50)
    print("  新能源OBD检测系统已启动")
    print(f"  模式: {'模拟' if SIMULATE else '真实ELM327'}")
    print("  浏览器访问: http://0.0.0.0:5000")
    print("=" * 50)
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)
