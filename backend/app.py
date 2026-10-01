#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

STATUS_FILE = Path(os.environ.get("QMI5G_STATUS_FILE", "/tmp/qmi5g-dashboard/status.json"))
STATIC_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="QMI 5G Dashboard", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def load_status() -> Dict[str, Any]:
    if not STATUS_FILE.exists():
        return {
            "available": False,
            "error": f"{STATUS_FILE} not found. Is qmi5g_collector.py running?",
        }

    try:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        data["available"] = True
        return data
    except Exception as exc:
        return {
            "available": False,
            "error": f"Failed to read status file: {exc}",
        }


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/api/status")
async def api_status() -> JSONResponse:
    return JSONResponse(load_status())


@app.get("/api/health")
async def api_health() -> JSONResponse:
    status = load_status()
    return JSONResponse(
        {
            "ok": bool(status.get("available")),
            "status_file": str(STATUS_FILE),
        }
    )


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket) -> None:
    await websocket.accept()

    try:
        while True:
            await websocket.send_json(load_status())
            await asyncio.sleep(1.0)
    except (WebSocketDisconnect, RuntimeError):
        pass
