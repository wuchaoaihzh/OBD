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
                "mode":             "模拟",
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


# ── 真实ELM327连接（占位，待接硬件后完善） ────────────────────────────────────
class RealOBD:
    def __init__(self, port="192.168.0.10:35000", baudrate=38400):
        self.port = port
        self.baudrate = baudrate
        self._conn = None
        self._lock = threading.Lock()

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

    def read_all(self) -> dict:
        with self._lock:
            speed   = self._query("SPEED")
            soc_raw = self._query("HYBRID_BATTERY_REMAINING")
            coolant = self._query("COOLANT_TEMP")
            dtc_resp = self._conn.query(obd.commands.GET_DTC) if self._conn else None
            dtcs = []
            if dtc_resp and not dtc_resp.is_null():
                dtcs = [str(d[0]) for d in dtc_resp.value]
            return {
                "timestamp":   datetime.now().strftime("%H:%M:%S"),
                "connected":   self._conn.is_connected() if self._conn else False,
                "mode":        "真实",
                "soc":         round(float(soc_raw), 1) if soc_raw else None,
                "soh":         None,
                "batt_voltage":None,
                "batt_current":None,
                "batt_temp":   round(float(coolant), 1) if coolant else None,
                "speed":       round(float(speed), 1) if speed else 0,
                "motor_temp":  None,
                "power_kw":    None,
                "charging":    None,
                "charge_pct":  round(float(soc_raw), 1) if soc_raw else None,
                "dtc_codes":   dtcs,
                "dtc_count":   len(dtcs),
                "charge_count":None,
                "full_charge_count": None,
                "total_mileage": None,
                "range_estimate": None,
            }

    def get_cell_data(self) -> dict:
        # 真实车辆需要Mode 22私有PID，ELM327到货后对照实车补充
        return {"cells": [], "cell_count": 0, "diff_mv": 0,
                "diff_warn": False, "diff_alarm": False, "temps": []}

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
        return {}

    def disconnect(self):
        if self._conn:
            self._conn.close()


# ── 工厂函数 ───────────────────────────────────────────────────────────────────
def create_obd_client(simulate=True, port="192.168.0.10:35000"):
    if simulate:
        print("[OBD] 使用模拟模式")
        return SimulatedOBD()
    print(f"[OBD] 尝试连接 {port} ...")
    client = RealOBD(port=port)
    if client.connect():
        print("[OBD] 连接成功！")
        return client
    print("[OBD] 连接失败，回退到模拟模式")
    return SimulatedOBD()
