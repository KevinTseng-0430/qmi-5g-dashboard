#!/usr/bin/env python3
"""
SIM8200EA-M2 + OAI 5G SA monitor collector.

Validated data sources:
- QMI NAS --nas-get-signal-info:
    5G RSRP / RSRQ / SNR
- QMI NAS --nas-get-serving-system:
    registration / PS attach / RAT / PLMN / roaming
- QMI WDS --wds-get-current-settings:
    IP / subnet / gateway / DNS / MTU
- QMI WDS --wds-get-default-settings=3gpp:
    APN / PDP type
- Linux sysfs:
    wwan0 RX/TX byte counters -> realtime Mbps

The collector is read-only. It does not register/deregister the modem and
does not start/stop a PDU session.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


DEFAULT_DEVICE = "/dev/cdc-wdm0"
DEFAULT_IFACE = "wwan0"
DEFAULT_OUTPUT = os.environ.get("QMI5G_STATUS_FILE", "/tmp/qmi5g-dashboard/status.json")


def run_qmicli(device: str, operation: str, timeout: float = 6.0) -> str:
    """Run one read-only qmicli operation and return stdout."""
    cmd = (["qmicli"] if os.geteuid() == 0 else ["sudo", "qmicli"]) + ["-d", device, "-p", operation]
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        msg = proc.stderr.strip() or proc.stdout.strip() or f"exit={proc.returncode}"
        raise RuntimeError(msg)
    return proc.stdout


def extract_quoted_number(text: str, label: str) -> Optional[float]:
    m = re.search(rf"{re.escape(label)}:\s*'([-+]?\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else None


def parse_signal_info(text: str) -> Dict[str, Any]:
    """Parse NR values only from the 5G section."""
    fiveg = re.search(r"(?ms)^5G:\s*(.*?)(?=^[A-Za-z0-9].*?:|\Z)", text)
    block = fiveg.group(1) if fiveg else text

    return {
        "rsrp_dbm": extract_quoted_number(block, "RSRP"),
        "rsrq_db": extract_quoted_number(block, "RSRQ"),
        "snr_db": extract_quoted_number(block, "SNR"),
    }


def first_quoted(text: str, label: str) -> Optional[str]:
    m = re.search(rf"{re.escape(label)}:\s*'([^']*)'", text)
    return m.group(1) if m else None


def parse_serving_system(text: str) -> Dict[str, Any]:
    registration = first_quoted(text, "Registration state")
    ps = first_quoted(text, "PS")
    roaming = first_quoted(text, "Roaming status")

    radio_match = re.search(r"\[\d+\]:\s*'([^']+)'", text)
    rat = radio_match.group(1) if radio_match else None

    current_plmn = re.search(
        r"(?ms)Current PLMN:\s*"
        r"\s*MCC:\s*'([^']+)'\s*"
        r"\s*MNC:\s*'([^']+)'",
        text,
    )
    mcc = current_plmn.group(1) if current_plmn else None
    mnc = current_plmn.group(2) if current_plmn else None

    pcs_match = re.search(r"MNC with PCS digit:\s*'([^']+)'", text)
    pcs_digit = pcs_match.group(1).lower() if pcs_match else None

    plmn = None
    if mcc is not None and mnc is not None:
        mcc_norm = mcc.zfill(3)
        if pcs_digit == "yes":
            mnc_norm = mnc.zfill(3)
        else:
            mnc_norm = mnc.zfill(2)
        plmn = mcc_norm + mnc_norm

    return {
        "registration": registration,
        "packet_service": ps,
        "rat": rat,
        "roaming": None if roaming is None else roaming == "on",
        "mcc": mcc.zfill(3) if mcc is not None else None,
        "mnc": (mnc.zfill(3) if pcs_digit == "yes" else mnc.zfill(2))
        if mnc is not None
        else None,
        "plmn": plmn,
    }


def parse_current_settings(text: str) -> Dict[str, Any]:
    def value(label: str) -> Optional[str]:
        m = re.search(rf"{re.escape(label)}:\s*([^\n]+)", text)
        if not m:
            return None
        return m.group(1).strip().strip("'")

    ip = value("IPv4 address")
    mask = value("IPv4 subnet mask")
    gateway = value("IPv4 gateway address")
    dns1 = value("IPv4 primary DNS")
    dns2 = value("IPv4 secondary DNS")
    mtu_raw = value("MTU")

    prefix = None
    if mask:
        try:
            prefix = ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen
        except ValueError:
            pass

    mtu = None
    if mtu_raw:
        try:
            mtu = int(mtu_raw)
        except ValueError:
            pass

    return {
        "ip_family": value("IP Family"),
        "ipv4": ip,
        "prefix_length": prefix,
        "netmask": mask,
        "gateway": gateway,
        "dns_primary": dns1,
        "dns_secondary": dns2,
        "mtu": mtu,
    }


def parse_default_settings(text: str) -> Dict[str, Any]:
    def q(label: str) -> Optional[str]:
        return first_quoted(text, label)

    return {
        "apn": q("APN"),
        "pdp_type": q("PDP type"),
        "auth": q("Auth"),
    }


def read_counter(iface: str, name: str) -> int:
    p = Path(f"/sys/class/net/{iface}/statistics/{name}")
    return int(p.read_text().strip())


def interface_state(iface: str) -> Dict[str, Any]:
    """Return Linux interface state suitable for raw-IP WWAN devices.

    qmi_wwan/raw-IP interfaces commonly report operstate='unknown' even when
    the interface is administratively UP and usable. Therefore, use IFF_UP
    from /sys/class/net/<iface>/flags as the primary up/down indicator and
    expose operstate separately.
    """
    base = Path(f"/sys/class/net/{iface}")

    admin_up: Optional[bool] = None
    lower_up: Optional[bool] = None
    operstate: Optional[str] = None
    flags_hex: Optional[str] = None

    try:
        operstate = (base / "operstate").read_text().strip()
    except OSError:
        pass

    try:
        flags_hex = (base / "flags").read_text().strip()
        flags = int(flags_hex, 16)
        admin_up = bool(flags & 0x1)  # IFF_UP
    except (OSError, ValueError):
        pass

    # For WWAN/raw-IP, carrier=1 is a better indication of LOWER_UP than
    # operstate, which may legitimately remain "unknown".
    try:
        lower_up = (base / "carrier").read_text().strip() == "1"
    except OSError:
        pass

    return {
        "interface_up": admin_up,
        "admin_up": admin_up,
        "lower_up": lower_up,
        "operstate": operstate,
        "flags": flags_hex,
    }


def atomic_write_json(path: str, payload: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, target)


class Collector:
    def __init__(self, device: str, iface: str, polling: Optional[Dict[str, float]] = None):
        self.device = device
        self.iface = iface
        polling = polling or {}
        self.signal_interval = float(polling.get("signal_interval_sec", 2.0))
        self.serving_interval = float(polling.get("serving_interval_sec", 5.0))
        self.network_interval = float(polling.get("network_interval_sec", 5.0))
        self.profile_interval = float(polling.get("profile_interval_sec", 30.0))

        self.signal: Dict[str, Any] = {}
        self.serving: Dict[str, Any] = {}
        self.network: Dict[str, Any] = {}
        self.profile: Dict[str, Any] = {}

        self.errors: Dict[str, str] = {}

        self.last_rx: Optional[int] = None
        self.last_tx: Optional[int] = None
        self.last_traffic_t: Optional[float] = None

        self.next_signal = 0.0
        self.next_serving = 0.0
        self.next_network = 0.0
        self.next_profile = 0.0

    def _poll(
        self,
        key: str,
        operation: str,
        parser,
    ) -> Dict[str, Any]:
        try:
            raw = run_qmicli(self.device, operation)
            parsed = parser(raw)
            self.errors.pop(key, None)
            return parsed
        except Exception as exc:
            self.errors[key] = str(exc)
            return {}

    def update_slow_metrics(self, now: float) -> None:
        # RF metrics: every 2 s.
        if now >= self.next_signal:
            new = self._poll(
                "signal",
                "--nas-get-signal-info",
                parse_signal_info,
            )
            if new:
                self.signal = new
            self.next_signal = now + self.signal_interval

        # Registration / PLMN / RAT: every 5 s.
        if now >= self.next_serving:
            new = self._poll(
                "serving_system",
                "--nas-get-serving-system",
                parse_serving_system,
            )
            if new:
                self.serving = new
            self.next_serving = now + self.serving_interval

        # IP / gateway / DNS / MTU: every 5 s.
        if now >= self.next_network:
            new = self._poll(
                "current_settings",
                "--wds-get-current-settings",
                parse_current_settings,
            )
            if new:
                self.network = new
            self.next_network = now + self.network_interval

        # APN changes rarely: every 30 s.
        if now >= self.next_profile:
            new = self._poll(
                "default_profile",
                "--wds-get-default-settings=3gpp",
                parse_default_settings,
            )
            if new:
                self.profile = new
            self.next_profile = now + self.profile_interval

    def traffic(self, now: float) -> Dict[str, Any]:
        try:
            rx = read_counter(self.iface, "rx_bytes")
            tx = read_counter(self.iface, "tx_bytes")
            self.errors.pop("traffic", None)
        except Exception as exc:
            self.errors["traffic"] = str(exc)
            return {
                "rx_bytes": None,
                "tx_bytes": None,
                "rx_mbps": None,
                "tx_mbps": None,
            }

        rx_mbps = None
        tx_mbps = None

        if (
            self.last_rx is not None
            and self.last_tx is not None
            and self.last_traffic_t is not None
        ):
            dt = now - self.last_traffic_t
            if dt > 0:
                # Handle interface reset/counter wrap conservatively.
                drx = max(0, rx - self.last_rx)
                dtx = max(0, tx - self.last_tx)
                rx_mbps = drx * 8.0 / dt / 1_000_000.0
                tx_mbps = dtx * 8.0 / dt / 1_000_000.0

        self.last_rx = rx
        self.last_tx = tx
        self.last_traffic_t = now

        return {
            "rx_bytes": rx,
            "tx_bytes": tx,
            "rx_mbps": None if rx_mbps is None else round(rx_mbps, 3),
            "tx_mbps": None if tx_mbps is None else round(tx_mbps, 3),
        }

    def sample(self) -> Dict[str, Any]:
        now = time.monotonic()
        self.update_slow_metrics(now)
        traffic = self.traffic(now)

        return {
            "timestamp": datetime.now(timezone.utc).astimezone().isoformat(
                timespec="seconds"
            ),
            "device": {
                "qmi": self.device,
                "interface": self.iface,
                **interface_state(self.iface),
            },
            "cellular": {
                **self.serving,
                **self.signal,
            },
            "data_session": {
                **self.profile,
                **self.network,
            },
            "traffic": traffic,
            "errors": dict(self.errors),
        }


def load_config(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("Top-level config must be a mapping")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only SIM8200EA-M2 QMI/Linux status collector"
    )
    parser.add_argument("--config", default=None, help="YAML config file")
    parser.add_argument("--device", default=None)
    parser.add_argument("--iface", default=None)
    parser.add_argument(
        "--interval",
        type=float,
        default=None,
        help="JSON output interval in seconds",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="latest JSON file",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="print one snapshot and exit",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="print compact JSON rather than pretty JSON",
    )
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except Exception as exc:
        parser.error(str(exc))

    device = args.device or config.get("qmi_device") or DEFAULT_DEVICE
    iface = args.iface or config.get("interface") or DEFAULT_IFACE
    output = args.output or config.get("status_file") or DEFAULT_OUTPUT
    polling = config.get("polling") or {}
    interval = args.interval
    if interval is None:
        interval = float(polling.get("output_interval_sec", 1.0))

    if interval <= 0:
        parser.error("--interval must be > 0")

    collector = Collector(device, iface, polling=polling)

    def emit(payload: Dict[str, Any]) -> None:
        atomic_write_json(output, payload)
        if args.compact:
            print(json.dumps(payload, ensure_ascii=False), flush=True)
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)

    if args.once:
        # First sample initializes RX/TX counters. A second sample gives a real rate.
        collector.sample()
        time.sleep(interval)
        emit(collector.sample())
        return 0

    try:
        while True:
            started = time.monotonic()
            emit(collector.sample())
            elapsed = time.monotonic() - started
            time.sleep(max(0.0, interval - elapsed))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
