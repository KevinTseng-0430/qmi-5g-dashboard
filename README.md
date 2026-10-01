# QMI 5G Dashboard

A lightweight, read-only web dashboard for monitoring Linux QMI-based 5G modems in real time.

Initially developed and validated with a **SIMCom SIM8200EA-M2** on a Raspberry Pi connected to an **OAI 5G SA** testbed.

<img width="1232" height="1098" alt="Screenshot 2026-10-01 at 14-44-05" src="https://github.com/user-attachments/assets/104928c4-32b9-47b8-b7c6-1fa751bb7a91" />


## Features

- 5G NR RSRP / RSRQ / SNR
- Registration / PS attach / RAT / PLMN / roaming
- APN / PDP type
- UE IP / prefix / gateway / DNS / MTU
- Real-time RX / TX Mbps from Linux interface counters
- Browser dashboard with WebSocket live updates
- REST JSON API
- No AT serial-port polling required for normal monitoring
- Read-only monitoring path: no register/deregister or PDU-session control

## Tested environment

- SIMCom SIM8200EA-M2 (Waveshare)
- Raspberry Pi 4
- Linux `qmi_wwan`
- `libqmi-utils` / `qmicli`
- `wwan0` raw-IP
- 5G NR SA n78
- OAI gNB + USRP B210
- OAI 5GC

Compatibility with other QMI-capable modems is a project goal, but is not yet guaranteed.

## Architecture

```text
QMI modem
   |
   +-- QMI NAS ----------------------+
   |  RSRP / RSRQ / SNR              |
   |  PLMN / RAT / registration      |
   |                                 |
   +-- QMI WDS ----------------------+--> qmi5g_collector.py
   |  APN / IP / gateway / MTU       |          |
   |                                 |          v
   +-- Linux wwan0 ------------------+   status.json
      RX/TX byte counters                       |
                                                v
                                          FastAPI
                                      REST + WebSocket
                                                |
                                                v
                                            Browser
```

## Data sources

| Metric | Source |
|---|---|
| RSRP / RSRQ / SNR | `qmicli --nas-get-signal-info` |
| Registration / PS / RAT / PLMN / roaming | `qmicli --nas-get-serving-system` |
| IP / subnet / gateway / DNS / MTU | `qmicli --wds-get-current-settings` |
| APN / PDP type | `qmicli --wds-get-default-settings=3gpp` |
| RX / TX rate | `/sys/class/net/<iface>/statistics/{rx,tx}_bytes` |

## Quick start

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip libqmi-utils

cd qmi-5g-dashboard

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

sudo mkdir -p /tmp/qmi5g-dashboard
sudo chmod 777 /tmp/qmi5g-dashboard
```

Start collector:

```bash
sudo .venv/bin/python collector/qmi5g_collector.py --config config.yaml
```

Start dashboard in another terminal:

```bash
source .venv/bin/activate
QMI5G_STATUS_FILE=/tmp/qmi5g-dashboard/status.json \
python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

Open:

```text
http://<Raspberry-Pi-IP>:8000
```

## API

```bash
curl http://127.0.0.1:8000/api/status
curl http://127.0.0.1:8000/api/health
```

WebSocket:

```text
ws://<host>:8000/ws/live
```

## Configuration

Edit `config.yaml` to change the QMI device, WWAN interface, status-file path, polling cadence, and documented Web defaults. CLI arguments override the collector defaults.

## Security

v0.1 is intentionally monitor-only. The Web API does not expose modem-control operations such as registration, CFUN reset, profile mutation, or PDU-session start/stop.

Bind the service only to trusted networks unless you add authentication and TLS.

## Roadmap

### v0.1
- [x] RSRP / RSRQ / SNR
- [x] PLMN / RAT / registration
- [x] APN / IP / gateway
- [x] RX / TX throughput
- [x] REST API
- [x] WebSocket dashboard
- [x] systemd examples

### v0.2
- [ ] band
- [ ] cell ID
- [ ] NR-ARFCN
- [ ] explicit PDU-session state
- [ ] longer history
- [ ] Prometheus exporter

### v0.3
- [ ] multi-modem support
- [ ] Docker deployment
- [ ] automatic capability detection

## Contributing

Compatibility reports and pull requests are welcome. Please include modem model, Linux distribution, kernel version, `qmicli --version`, driver, link-layer format, and relevant QMI outputs. Redact subscriber identifiers and credentials before posting logs.

## License

MIT
