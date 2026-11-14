"""
obd_client.py — ELM327 OBD连接层
支持真实ELM327 WiFi连接 和 模拟模式
"""

try:
    import obd
    OBD_AVAILABLE = True
except ImportError:
    OBD_AVAILABLE = False

import random
import time
import threading
from datetime import datetime


# ── 模拟数据生成器 ─────────────────────────────────────────────────────────────
class SimulatedOBD:
    """无硬件时使用，生成逼真的新能源模拟数据"""

    CELL_COUNT = 96  # 汉EV 刀片电池单体数量

    def __init__(self):
        self._soc = 78.0
        self._soh = 95.5
        self._speed = 0.0
        self._charging = False
        self._motor_temp = 35.0
        self._charge_count = 312
        self._full_charge_count = 48
        self._total_mileage = 28650.0
        self._fault_codes = []
        self._lock = threading.Lock()
        # 初始化单体电压（模拟96节）
        self._cells = [round(3.65 + random.uniform(-0.03, 0.03), 3)
                       for _ in range(self.CELL_COUNT)]
        # 单体温度（16个温度采集点）
        self._cell_temps = [round(28 + random.uniform(-2, 4), 1)
                            for _ in range(16)]

    def _drift(self, val, lo, hi, step=0.5):
        return max(lo, min(hi, val + random.uniform(-step, step)))

    def update(self):
        with self._lock:
            self._speed = self._drift(self._speed, 0, 120, 3)
            self._motor_temp = self._drift(self._motor_temp, 25, 90, 0.8)
            if self._speed > 5:
                self._soc = max(0, self._soc - random.uniform(0, 0.05))
            if self._soc < 20:
                self._charging = True
            if self._soc > 95:
                self._charging = False
            if self._charging:
                self._soc = min(100, self._soc + random.uniform(0.1, 0.3))
                self._charge_count += 0  # 只在完整充电周期计数
            # 单体电压小幅漂移
            for i in range(self.CELL_COUNT):
                self._cells[i] = round(
                    self._drift(self._cells[i], 3.0, 4.2, 0.005), 3)
            # 单体温度漂移
            for i in range(16):
                self._cell_temps[i] = round(
                    self._drift(self._cell_temps[i], 15, 55, 0.3), 1)

    def read_all(self) -> dict:
        self.update()
        with self._lock:
            batt_curr = round((-30 if self._charging else self._speed * 0.8)
                              + random.uniform(-2, 2), 1)
            batt_volt = round(350 + random.uniform(-5, 5), 1)
            return {
                "timestamp":        datetime.now().strftime("%H:%M:%S"),
                "connected":        True,
                "mode":             getattr(self, '_mode_label', '模拟模式'),
                "soc":              round(self._soc, 1),
                "soh":              round(self._soh, 1),
                "batt_voltage":     batt_volt,
                "batt_current":     batt_curr,
                "batt_temp":        round(28 + random.uniform(-2, 5), 1),
                "speed":            round(self._speed, 1),
                "motor_temp":       round(self._motor_temp, 1),
                "power_kw":         round(batt_volt * abs(batt_curr) / 1000 *
                                         (-1 if self._charging else 1), 1),
                "charging":         self._charging,
                "charge_pct":       round(self._soc, 1),
                "dtc_codes":        list(self._fault_codes),
                "dtc_count":        len(self._fault_codes),
                "charge_count":     self._charge_count,
                "full_charge_count":self._full_charge_count,
                "total_mileage":    round(self._total_mileage, 1),
                "range_estimate":   round(self._soc * 6.05, 0),  # 汉EV续航估算
            }

    def get_cell_data(self) -> dict:
        """返回单体电压和温度详情"""
        self.update()
        with self._lock:
            cells = list(self._cells)
            temps = list(self._cell_temps)
            max_v = max(cells)
            min_v = min(cells)
            avg_v = round(sum(cells) / len(cells), 3)
            diff  = round((max_v - min_v) * 1000, 1)  # 压差mV
            return {
                "cells":       cells,
                "cell_count":  len(cells),
                "max_voltage": round(max_v, 3),
                "min_voltage": round(min_v, 3),
                "avg_voltage": avg_v,
                "diff_mv":     diff,
                "diff_warn":   diff > 50,   # 压差超50mV预警
                "diff_alarm":  diff > 100,  # 压差超100mV报警
                "temps":       temps,
                "max_temp":    max(temps),
                "min_temp":    min(temps),
            }

    def get_dtc(self) -> list:
        with self._lock:
            return list(self._fault_codes)

    def scan_all_systems(self) -> dict:
        """模拟全车系统扫描"""
        systems = {
            "BMS电池管理": [],
            "电机控制器":  [],
            "整车控制器":  [],
            "车身控制":    [],
            "充电系统":    [],
        }
        # 加入已注入的故障码到BMS
        with self._lock:
            for code in self._fault_codes:
                systems["BMS电池管理"].append({
                    "code": code,
                    "desc": DTC_DESC.get(code, "未知故障"),
                    "level": "严重" if code.startswith("P0A8") else "警告",
                })
        return systems

    def clear_dtc(self) -> bool:
        with self._lock:
            self._fault_codes = []
        return True

    def inject_fault(self, code: str):
        with self._lock:
            if code not in self._fault_codes:
                self._fault_codes.append(code)

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "charge_count":      self._charge_count,
                "full_charge_count": self._full_charge_count,
                "total_mileage":     round(self._total_mileage, 1),
                "soh":               round(self._soh, 1),
                "range_estimate":    round(self._soc * 6.05, 0),
                "avg_energy":        round(14.2 + random.uniform(-0.5, 0.5), 1),
                "batt_age_days":     1580,
            }


# ── 故障码描述表 ───────────────────────────────────────────────────────────────
DTC_DESC = {
    "P0A80": "电池组严重退化",
    "P0A7A": "电池冷却系统故障",
    "P0B00": "高压互锁回路故障",
    "P1E00": "电机控制器通信超时",
    "P0AFA": "电池系统电压过低",
    "P0A9B": "电池温度传感器故障",
    "P0AA6": "高压隔离故障",
    "P0AC0": "驱动电机A温度过高",
    "P0562": "系统电压低",
    "U0100": "与ECM/PCM通信丢失",
}


# ── 比亚迪汉EV Mode 22 私有PID表 ──────────────────────────────────────────────
# 来源：社区逆向整理（非官方，实车需验证缩放系数）
# 格式：名称: (PID十六进制, 缩放系数, 偏移, 单位)
HAN_EV_PIDS = {
    # BMS基础数据
    "SOC":          (0x1001, 0.4,    0,    "%"),       # 字节*0.4 = SOC%
    "SOH":          (0x1002, 0.4,    0,    "%"),       # 字节*0.4 = SOH%
    "BATT_VOLT":    (0x1003, 0.1,    0,    "V"),       # 2字节大端*0.1
    "BATT_CURR":    (0x1004, 0.1, -3000,  "A"),       # 2字节大端*0.1-3000（负=放电）
    "BATT_TEMP_MAX":(0x1005, 1,    -40,   "℃"),       # 字节-40
    "BATT_TEMP_MIN":(0x1006, 1,    -40,   "℃"),
    "CHARGE_COUNT": (0x1010, 1,      0,    "次"),
    "FULL_CHARGE":  (0x1011, 1,      0,    "次"),
    "TOTAL_MILEAGE":(0x1012, 1,      0,    "km"),      # 3字节
    # 单体电压（96节，每次读8节，共12个PID）
    # 0x1020~0x102B 每个返回8节电压，每节2字节，单位0.001V
    "CELL_V_01_08": (0x1020, 0.001,  0,   "V"),
    "CELL_V_09_16": (0x1021, 0.001,  0,   "V"),
    "CELL_V_17_24": (0x1022, 0.001,  0,   "V"),
    "CELL_V_25_32": (0x1023, 0.001,  0,   "V"),
    "CELL_V_33_40": (0x1024, 0.001,  0,   "V"),
    "CELL_V_41_48": (0x1025, 0.001,  0,   "V"),
    "CELL_V_49_56": (0x1026, 0.001,  0,   "V"),
    "CELL_V_57_64": (0x1027, 0.001,  0,   "V"),
    "CELL_V_65_72": (0x1028, 0.001,  0,   "V"),
    "CELL_V_73_80": (0x1029, 0.001,  0,   "V"),
    "CELL_V_81_88": (0x102A, 0.001,  0,   "V"),
    "CELL_V_89_96": (0x102B, 0.001,  0,   "V"),
    # 温度采集点（16个）
    "CELL_T_01_08": (0x1030, 1,    -40,   "℃"),
    "CELL_T_09_16": (0x1031, 1,    -40,   "℃"),
    # 电机
    "MOTOR_TEMP":   (0x2001, 1,    -40,   "℃"),
    "MOTOR_RPM":    (0x2002, 1,      0,   "rpm"),
    "MOTOR_TORQUE": (0x2003, 0.1,    0,   "Nm"),
}

CELL_PID_KEYS = [
    "CELL_V_01_08","CELL_V_09_16","CELL_V_17_24","CELL_V_25_32",
    "CELL_V_33_40","CELL_V_41_48","CELL_V_49_56","CELL_V_57_64",
    "CELL_V_65_72","CELL_V_73_80","CELL_V_81_88","CELL_V_89_96",
]
TEMP_PID_KEYS = ["CELL_T_01_08", "CELL_T_09_16"]


# ── 真实ELM327连接 ─────────────────────────────────────────────────────────────
class RealOBD:
    def __init__(self, port="192.168.0.10:35000", baudrate=38400, car_model="han_ev"):
        self.port = port
        self.baudrate = baudrate
        self.car_model = car_model
        self._conn = None
        self._lock = threading.Lock()
        self._host = None
        self._port_num = None

    def connect(self) -> bool:
        if not OBD_AVAILABLE:
            return False
        try:
            if ":" in self.port and not self.port.startswith("/"):
                host, p = self.port.split(":")
                connection_str = f"socket://{host}:{p}"
            else:
                connection_str = self.port
            self._conn = obd.OBD(portstr=connection_str,
                                  baudrate=self.baudrate, fast=False, timeout=5)
            # 同时保存socket用于发送原始AT指令
            self._host = host if ":" in self.port else None
            self._port_num = int(p) if ":" in self.port else None
            return self._conn.is_connected()
        except Exception as e:
            print(f"[OBD] 连接失败: {e}")
            return False

    def _query(self, cmd_name):
        if not self._conn or not self._conn.is_connected():
            return None
        try:
            cmd = obd.commands[cmd_name]
            resp = self._conn.query(cmd)
            if resp.is_null():
                return None
            return resp.value.magnitude if hasattr(resp.value, "magnitude") else resp.value
        except Exception:
            return None

    def _mode22(self, pid_hex: int, timeout=2.0):
        """
        发送 Mode 22 (22 xxxx) 原始指令，返回响应字节列表。
        ELM327 WiFi版通过socket直接发AT指令。
        返回 None 表示失败或无响应。
        """
        import socket as _socket
        try:
            s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((self._host, self._port_num))
            # 发送指令：22 高字节 低字节
            hi = (pid_hex >> 8) & 0xFF
            lo = pid_hex & 0xFF
            cmd = f"22{hi:02X}{lo:02X}\r"
            s.sendall(cmd.encode())
            time.sleep(0.3)
            raw = b""
            try:
                while True:
                    chunk = s.recv(256)
                    if not chunk:
                        break
                    raw += chunk
                    if b">" in raw:
                        break
            except Exception:
                pass
            s.close()
            # 解析响应：找到 62 xx xx 开头的数据行
            resp_str = raw.decode("ascii", errors="ignore")
            for line in resp_str.split("\r"):
                line = line.strip().replace(" ", "").upper()
                if line.startswith("62"):
                    # 去掉前3字节头（62 HH LL），剩下是数据
                    data_hex = line[6:]
                    return [int(data_hex[i:i+2], 16)
                            for i in range(0, len(data_hex)-1, 2)]
            return None
        except Exception as e:
            print(f"[Mode22] PID {pid_hex:04X} 失败: {e}")
            return None

    def _parse_pid(self, key: str, raw_bytes: list):
        """根据PID定义解析原始字节"""
        if not raw_bytes:
            return None
        pid_hex, scale, offset, unit = HAN_EV_PIDS[key]
        try:
            if len(raw_bytes) == 1:
                val = raw_bytes[0]
            elif len(raw_bytes) >= 2:
                val = (raw_bytes[0] << 8) | raw_bytes[1]
            else:
                return None
            return round(val * scale + offset, 2)
        except Exception:
            return None

    def read_all(self) -> dict:
        with self._lock:
            # 标准OBD-II
            speed   = self._query("SPEED")
            dtc_resp = self._conn.query(obd.commands.GET_DTC) if self._conn else None
            dtcs = []
            if dtc_resp and not dtc_resp.is_null():
                dtcs = [str(d[0]) for d in dtc_resp.value]

            # 汉EV Mode 22 私有PID
            soc      = self._parse_pid("SOC",       self._mode22(0x1001))
            soh      = self._parse_pid("SOH",       self._mode22(0x1002))
            bv_raw   = self._mode22(0x1003)
            bi_raw   = self._mode22(0x1004)
            bt_max   = self._parse_pid("BATT_TEMP_MAX", self._mode22(0x1005))
            motor_t  = self._parse_pid("MOTOR_TEMP",    self._mode22(0x2001))

            # 电压：2字节大端
            batt_v = None
            if bv_raw and len(bv_raw) >= 2:
                batt_v = round(((bv_raw[0] << 8) | bv_raw[1]) * 0.1, 1)
            # 电流：2字节大端，偏移-3000
            batt_i = None
            if bi_raw and len(bi_raw) >= 2:
                batt_i = round(((bi_raw[0] << 8) | bi_raw[1]) * 0.1 - 3000, 1)

            charging = None
            if batt_i is not None:
                charging = batt_i < 0  # 负电流=充电

            power_kw = None
            if batt_v and batt_i:
                power_kw = round(batt_v * abs(batt_i) / 1000 *
                                 (-1 if charging else 1), 1)

            return {
                "timestamp":        datetime.now().strftime("%H:%M:%S"),
                "connected":        self._conn.is_connected() if self._conn else False,
                "mode":             "汉EV",
                "soc":              soc,
                "soh":              soh,
                "batt_voltage":     batt_v,
                "batt_current":     batt_i,
                "batt_temp":        bt_max,
                "speed":            round(float(speed), 1) if speed else 0,
                "motor_temp":       motor_t,
                "power_kw":         power_kw,
                "charging":         charging,
                "charge_pct":       soc,
                "dtc_codes":        dtcs,
                "dtc_count":        len(dtcs),
                "charge_count":     self._parse_pid("CHARGE_COUNT", self._mode22(0x1010)),
                "full_charge_count":self._parse_pid("FULL_CHARGE",  self._mode22(0x1011)),
                "total_mileage":    self._read_mileage(),
                "range_estimate":   round(soc * 6.05, 0) if soc else None,
            }

    def _read_mileage(self):
        """里程3字节"""
        raw = self._mode22(0x1012)
        if raw and len(raw) >= 3:
            return (raw[0] << 16) | (raw[1] << 8) | raw[2]
        return None

    def get_cell_data(self) -> dict:
        """读取96节单体电压 + 16点温度"""
        cells = []
        for key in CELL_PID_KEYS:
            pid = HAN_EV_PIDS[key][0]
            raw = self._mode22(pid)
            if raw and len(raw) >= 16:
                # 每节2字节，共8节
                for i in range(0, 16, 2):
                    v = round(((raw[i] << 8) | raw[i+1]) * 0.001, 3)
                    cells.append(v)
            else:
                # 读取失败补0（方便排查）
                cells.extend([0.0] * 8)

        temps = []
        for key in TEMP_PID_KEYS:
            pid = HAN_EV_PIDS[key][0]
            raw = self._mode22(pid)
            if raw:
                for b in raw[:8]:
                    temps.append(round(b - 40, 1))
            else:
                temps.extend([0.0] * 8)

        if not any(cells):
            return {"cells": [], "cell_count": 0, "diff_mv": 0,
                    "diff_warn": False, "diff_alarm": False, "temps": []}

        valid = [v for v in cells if v > 0]
        max_v = max(valid) if valid else 0
        min_v = min(valid) if valid else 0
        avg_v = round(sum(valid) / len(valid), 3) if valid else 0
        diff  = round((max_v - min_v) * 1000, 1)

        return {
            "cells":       cells,
            "cell_count":  len(cells),
            "max_voltage": round(max_v, 3),
            "min_voltage": round(min_v, 3),
            "avg_voltage": avg_v,
            "diff_mv":     diff,
            "diff_warn":   diff > 50,
            "diff_alarm":  diff > 100,
            "temps":       temps,
            "max_temp":    max(temps) if temps else 0,
            "min_temp":    min(temps) if temps else 0,
        }

    def get_dtc(self) -> list:
        with self._lock:
            if not self._conn:
                return []
            resp = self._conn.query(obd.commands.GET_DTC)
            if resp.is_null():
                return []
            return [str(d[0]) for d in resp.value]

    def scan_all_systems(self) -> dict:
        dtcs = self.get_dtc()
        result = {"全车扫描": []}
        for code in dtcs:
            result["全车扫描"].append({
                "code": code,
                "desc": DTC_DESC.get(code, "未知故障"),
                "level": "警告",
            })
        return result

    def clear_dtc(self) -> bool:
        with self._lock:
            if not self._conn:
                return False
            resp = self._conn.query(obd.commands.CLEAR_DTC)
            return not resp.is_null()

    def get_stats(self) -> dict:
        with self._lock:
            charge  = self._parse_pid("CHARGE_COUNT", self._mode22(0x1010))
            full    = self._parse_pid("FULL_CHARGE",  self._mode22(0x1011))
            mileage = self._read_mileage()
            soc_raw = self._mode22(0x1001)
            soc     = self._parse_pid("SOC", soc_raw)
            soh_raw = self._mode22(0x1002)
            soh     = self._parse_pid("SOH", soh_raw)
            return {
                "charge_count":      charge,
                "full_charge_count": full,
                "total_mileage":     mileage,
                "soh":               soh,
                "range_estimate":    round(soc * 6.05, 0) if soc else None,
                "avg_energy":        None,
                "batt_age_days":     None,
            }

    def disconnect(self):
        if self._conn:
            self._conn.close()


# ── EQ1 PID暴力扫描器 + CAN监听器 ─────────────────────────────────────────────
class EQ1Scanner:
    """
    奇瑞EQ1 数据获取方式：
    1. CAN监听模式（推荐）— 直接读取CAN总线广播的电压帧（0x541~0x557）
    2. Mode 22暴力扫描 — 扫描UDS诊断PID，适用于没有公开文档的车型
    """
    # CAN广播帧ID（来源：github.com/test3210-d/Chery-eq1-bms）
    VOLTAGE_FRAME_IDS = list(range(0x541, 0x558))  # 0x541~0x557，共23帧×4节=92节

    SCAN_RANGES = [
        (0x1000, 0x10FF),   # BMS常用区间
        (0x2000, 0x20FF),   # 电机控制
        (0x3000, 0x30FF),   # 整车控制
        (0xF400, 0xF4FF),   # 通用UDS数据标识
    ]

    def __init__(self, host="192.168.0.10", port=35000):
        self.host = host
        self.port = port
        self._results = {}
        self._progress = 0
        self._total = 0
        self._running = False
        self._lock = threading.Lock()

    def _send_at(self, cmd: str, timeout=1.0):
        """发送AT指令到ELM327"""
        import socket as _socket
        try:
            s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((self.host, self.port))
            s.sendall(f"{cmd}\r".encode())
            time.sleep(0.2)
            raw = b""
            try:
                while True:
                    chunk = s.recv(256)
                    if not chunk: break
                    raw += chunk
                    if b">" in raw: break
            except Exception:
                pass
            s.close()
            return raw.decode("ascii", errors="ignore").strip()
        except Exception as e:
            return f"ERROR: {e}"

    def listen_can(self, duration=10) -> dict:
        """
        CAN监听模式：捕获EQ1电压广播帧（0x541~0x557）。
        duration: 监听时长（秒），默认10秒
        返回：{"cells": [v1,v2,...], "raw_frames": {...}}
        """
        import socket as _socket
        print(f"[EQ1 CAN] 开始监听CAN总线，时长 {duration}s ...")

        # 初始化ELM327到CAN监听模式
        self._send_at("ATZ")      # 复位
        time.sleep(1)
        self._send_at("ATE0")     # 关闭回显
        self._send_at("ATH1")     # 显示CAN ID头部
        self._send_at("ATSP6")    # 设置协议为ISO 15765-4 CAN (500k)
        self._send_at("ATCAF0")   # 关闭CAN自动格式化

        # 开始监听所有CAN消息
        try:
            s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            s.settimeout(duration + 2)
            s.connect((self.host, self.port))
            s.sendall(b"ATMA\r")  # Monitor All

            raw_frames = {}
            start_time = time.time()
            buffer = b""

            while time.time() - start_time < duration:
                try:
                    chunk = s.recv(512)
                    if not chunk:
                        break
                    buffer += chunk

                    # 解析CAN帧（格式：ID DD DD DD ...）
                    lines = buffer.decode("ascii", errors="ignore").split("\r")
                    buffer = lines[-1].encode()  # 保留未完成行

                    for line in lines[:-1]:
                        line = line.strip().replace(" ", "").upper()
                        if len(line) < 6:
                            continue
                        # 提取CAN ID（前3个十六进制字符）
                        try:
                            can_id = int(line[:3], 16)
                            data_hex = line[3:]
                            if can_id in self.VOLTAGE_FRAME_IDS:
                                raw_frames[f"0x{can_id:03X}"] = data_hex
                        except Exception:
                            continue

                except _socket.timeout:
                    break

            # 发送中断停止监听
            s.sendall(b"\r")
            s.close()

        except Exception as e:
            print(f"[EQ1 CAN] 监听异常: {e}")
            return {"cells": [], "raw_frames": {}}

        # 解析电压数据
        cells = []
        for fid in range(0x541, 0x558):
            key = f"0x{fid:03X}"
            if key not in raw_frames:
                continue
            data_hex = raw_frames[key]
            # 每帧8字节，前4个字节是4节电压，每节2字节
            for i in range(0, min(8, len(data_hex)), 4):
                if i+3 < len(data_hex):
                    try:
                        v_raw = int(data_hex[i:i+4], 16)
                        cells.append(round(v_raw / 1000.0, 3))
                    except Exception:
                        cells.append(0.0)

        print(f"[EQ1 CAN] 捕获到 {len(raw_frames)} 个电压帧，解析出 {len(cells)} 节单体")
        return {
            "cells": cells,
            "cell_count": len(cells),
            "raw_frames": raw_frames,
            "max_voltage": round(max(cells), 3) if cells else 0,
            "min_voltage": round(min(cells), 3) if cells else 0,
            "avg_voltage": round(sum(cells)/len(cells), 3) if cells else 0,
            "diff_mv": round((max(cells)-min(cells))*1000, 1) if cells else 0,
        }

    def _send_mode22(self, pid_hex: int, timeout=1.0):
        import socket as _socket
        try:
            s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((self.host, self.port))
            hi = (pid_hex >> 8) & 0xFF
            lo = pid_hex & 0xFF
            s.sendall(f"22{hi:02X}{lo:02X}\r".encode())
            time.sleep(0.15)
            raw = b""
            try:
                while True:
                    chunk = s.recv(256)
                    if not chunk: break
                    raw += chunk
                    if b">" in raw: break
            except Exception:
                pass
            s.close()
            resp = raw.decode("ascii", errors="ignore")
            for line in resp.split("\r"):
                line = line.strip().replace(" ","").upper()
                if line.startswith("62"):
                    data_hex = line[6:]
                    return [int(data_hex[i:i+2],16)
                            for i in range(0, len(data_hex)-1, 2)]
            return None
        except Exception:
            return None

    def scan(self, progress_cb=None):
        """全量扫描，progress_cb(pct, found)回调进度"""
        self._running = True
        self._results = {}
        total = sum(hi - lo + 1 for lo, hi in self.SCAN_RANGES)
        self._total = total
        done = 0

        for lo, hi in self.SCAN_RANGES:
            for pid in range(lo, hi + 1):
                if not self._running:
                    break
                raw = self._send_mode22(pid)
                if raw:
                    self._results[f"0x{pid:04X}"] = {
                        "raw_hex":   " ".join(f"{b:02X}" for b in raw),
                        "raw_bytes": raw,
                        "len":       len(raw),
                        # 尝试常见解析
                        "as_uint8":  raw[0] if raw else None,
                        "as_uint16": ((raw[0]<<8)|raw[1]) if len(raw)>=2 else None,
                        "as_uint16_scaled_01": round(((raw[0]<<8)|raw[1])*0.1,2) if len(raw)>=2 else None,
                    }
                done += 1
                self._progress = done
                if progress_cb:
                    progress_cb(round(done/total*100, 1), len(self._results))

        # 保存结果
        import os, json
        out = os.path.join(os.path.dirname(__file__), "eq1_pids.json")
        with open(out, "w") as f:
            json.dump(self._results, f, indent=2, ensure_ascii=False)

        self._running = False
        return self._results

    def analyze(self) -> dict:
        """
        对扫描结果做特征匹配，自动推断每个PID的含义。
        返回按类型分组的候选列表。
        """
        import os, json
        path = os.path.join(os.path.dirname(__file__), "eq1_pids.json")
        if not os.path.exists(path):
            return {}
        with open(path) as f:
            raw_data = json.load(f)

        candidates = {
            "SOC电量%":    [],
            "SOH健康度%":  [],
            "总电压V":     [],
            "总电流A":     [],
            "单体电压V":   [],
            "电池温度℃":  [],
            "车速km/h":    [],
            "未知":        [],
        }

        for pid, d in raw_data.items():
            u8  = d.get("as_uint8")
            u16 = d.get("as_uint16")
            s01 = d.get("as_uint16_scaled_01")
            matched = False

            # SOC/SOH：单字节 0~100，或双字节*0.4在0~100
            if u8 is not None and 0 <= u8 <= 100:
                candidates["SOC电量%"].append({"pid": pid, "val": u8, "formula": "byte×1", "raw": d["raw_hex"]})
                matched = True
            elif u16 is not None and 0 <= u16 * 0.4 <= 100:
                v = round(u16 * 0.4, 1)
                candidates["SOC电量%"].append({"pid": pid, "val": v, "formula": "uint16×0.4", "raw": d["raw_hex"]})
                matched = True

            # 总电压：uint16*0.1 在 200~500V
            if s01 is not None and 200 <= s01 <= 500:
                candidates["总电压V"].append({"pid": pid, "val": s01, "formula": "uint16×0.1", "raw": d["raw_hex"]})
                matched = True

            # 单体电压：uint16*0.001 在 2.5~4.5V
            if u16 is not None and 2500 <= u16 <= 4500:
                v = round(u16 * 0.001, 3)
                candidates["单体电压V"].append({"pid": pid, "val": v, "formula": "uint16×0.001", "raw": d["raw_hex"]})
                matched = True

            # 温度：单字节-40 在 -20~80℃
            if u8 is not None and 20 <= u8 <= 120:  # -40偏移后 -20~80
                v = u8 - 40
                candidates["电池温度℃"].append({"pid": pid, "val": v, "formula": "byte-40", "raw": d["raw_hex"]})
                matched = True

            # 电流：uint16*0.1-3000 在 -500~500A
            if s01 is not None and -500 <= s01 - 3000 <= 500:
                v = round(s01 - 3000, 1)
                candidates["总电流A"].append({"pid": pid, "val": v, "formula": "uint16×0.1-3000", "raw": d["raw_hex"]})
                matched = True

            # 车速：单字节 0~200
            if u8 is not None and 0 <= u8 <= 200 and not matched:
                candidates["车速km/h"].append({"pid": pid, "val": u8, "formula": "byte×1", "raw": d["raw_hex"]})

        # 去掉空分类
        return {k: v for k, v in candidates.items() if v}

    def save_confirmed_config(self, confirmed: dict):
        """
        保存用户确认的PID配置到 eq1_config.json。
        confirmed格式：{"SOC": "0x1001", "total_voltage": "0x1003", ...}
        """
        import os, json
        path = os.path.join(os.path.dirname(__file__), "eq1_config.json")
        with open(path, "w") as f:
            json.dump(confirmed, f, indent=2, ensure_ascii=False)
        return path

    def export_report(self) -> str:
        """
        生成完整分析报告（给人工/AI分析用）。
        返回报告文本内容。
        """
        import os, json
        path = os.path.join(os.path.dirname(__file__), "eq1_pids.json")
        if not os.path.exists(path):
            return "无扫描数据"
        with open(path) as f:
            raw_data = json.load(f)

        lines = [
            "# 奇瑞EQ1 OBD PID扫描报告",
            f"# 扫描时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"# 有效PID数量：{len(raw_data)}",
            "",
            "## 自动分析候选",
        ]
        analysis = self.analyze()
        for category, items in analysis.items():
            lines.append(f"\n### {category}")
            for item in items:
                lines.append(f"  PID {item['pid']}  当前值={item['val']}  公式={item['formula']}  原始={item['raw']}")

        lines += ["", "## 完整原始数据", ""]
        for pid, d in raw_data.items():
            lines.append(f"PID {pid}: hex=[{d['raw_hex']}] len={d['len']} "
                         f"u8={d['as_uint8']} u16={d['as_uint16']} u16×0.1={d['as_uint16_scaled_01']}")

        report = "\n".join(lines)
        # 同时保存到文件
        rpath = os.path.join(os.path.dirname(__file__), "eq1_report.txt")
        with open(rpath, "w", encoding="utf-8") as f:
            f.write(report)
        return report
        with self._lock:
            return {
                "progress": self._progress,
                "total":    self._total,
                "pct":      round(self._progress/self._total*100,1) if self._total else 0,
                "found":    len(self._results),
                "running":  self._running,
            }


# 全局扫描器实例
_eq1_scanner = None


# ── 车型配置表 ─────────────────────────────────────────────────────────────────
CAR_MODELS = {
    "han_ev":   "比亚迪汉EV",
    "eq1":      "奇瑞小蚂蚁EQ1",
    "simulate": "模拟模式",
}


# ── 工厂函数 ───────────────────────────────────────────────────────────────────
def create_obd_client(simulate=True, port="192.168.0.10:35000", car_model="han_ev"):
    if simulate:
        print(f"[OBD] 使用模拟模式（车型: {car_model}）")
        client = SimulatedOBD()
        client._mode_label = "模拟模式"
        return client

    print(f"[OBD] 尝试连接 {port}，车型: {car_model} ...")
    client = RealOBD(port=port, car_model=car_model)
    if client.connect():
        print("[OBD] 连接成功！")
        client._mode_label = f"已连接·{CAR_MODELS.get(car_model, car_model)}"
        return client
    print("[OBD] 连接失败，回退到模拟模式")
    fallback = SimulatedOBD()
    fallback._mode_label = "模拟(无硬件)"
    return fallback


def get_eq1_scanner(port="192.168.0.10:35000"):
    """获取或创建EQ1扫描器实例"""
    global _eq1_scanner
    host, p = port.split(":") if ":" in port else (port, "35000")
    _eq1_scanner = EQ1Scanner(host=host, port=int(p))
    return _eq1_scanner
