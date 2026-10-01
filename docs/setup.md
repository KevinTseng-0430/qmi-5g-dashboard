# Setup

## Verify modem

```bash
ls -l /dev/cdc-wdm0
ip link show wwan0
sudo qmicli -d /dev/cdc-wdm0 -p --nas-get-serving-system
sudo qmicli -d /dev/cdc-wdm0 -p --nas-get-signal-info
```

## Verify link-layer format

```bash
sudo qmicli -d /dev/cdc-wdm0 -p --get-expected-data-format
sudo qmicli -d /dev/cdc-wdm0 -p --wda-get-data-format
```

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
sudo mkdir -p /tmp/qmi5g-dashboard
sudo chmod 777 /tmp/qmi5g-dashboard
```

## Run collector

```bash
sudo .venv/bin/python collector/qmi5g_collector.py --config config.yaml
```

## Run Web backend

```bash
source .venv/bin/activate
QMI5G_STATUS_FILE=/tmp/qmi5g-dashboard/status.json \
python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
```
