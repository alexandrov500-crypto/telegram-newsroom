#!/usr/bin/env python3
"""Refresh Xray (VLESS/Reality) outbound from a rotating Gram VPN subscription."""

from __future__ import annotations

import base64
import datetime
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from urllib.parse import parse_qs, unquote, urlparse

BASE = os.getenv("NEWSROOM_BASE", "/opt/newsroom")
URL_FILE = os.getenv("VPN_SUBSCRIPTION_FILE", f"{BASE}/deploy/timeweb/vpn_sub_url.txt")
CONFIG = f"{BASE}/xray-data/config.json"
SERVERS = f"{BASE}/xray-data/proxy_servers.json"
STATE = f"{BASE}/xray-data/active_server.json"
PREF_FILE = f"{BASE}/xray-data/vpn_pref.txt"
PROBE_IMAGE = os.getenv("VPN_PROBE_IMAGE", "vpn-probe:local")
XRAY_IMAGE = os.getenv("XRAY_IMAGE", "ghcr.io/xtls/xray-core:latest")
DC_HOST = "149.154.167.51"
DC_PORT = "443"
UA = "v2rayN/6.45"
PREF = [
    "Финлянд",
    "Нидерланд",
    "Герман",
    "Швеци",
    "Эстони",
    "Швейцар",
    "Литва",
    "Польш",
    "Дани",
    "Ирланд",
    "Великобритан",
]
EXCLUDE = ["Росси", "МТС", "Мегафон", "LTE", "Армени", "Украин", "Беларус"]


def log(msg: str) -> None:
    print(datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ") + " " + msg, flush=True)


def docker_network() -> str:
    try:
        r = subprocess.run(
            [
                "docker",
                "inspect",
                "xray",
                "--format",
                "{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        parts = r.stdout.strip().split()
        if parts:
            return parts[0]
    except Exception:
        pass
    return "telegram-newsroom-timeweb_default"


NET = docker_network()


def subscription_url() -> str:
    env_url = os.getenv("VPN_SUBSCRIPTION_URL", "").strip()
    if env_url:
        return env_url
    return open(URL_FILE).read().strip()


def fetch_servers() -> list[dict]:
    url = subscription_url()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    raw = urllib.request.urlopen(req, timeout=30).read().decode()
    try:
        dec = base64.b64decode(raw + "=" * (-len(raw) % 4)).decode()
    except Exception:
        dec = raw
    rows: list[dict] = []
    for ln in dec.splitlines():
        ln = ln.strip()
        if not ln.startswith("vless://"):
            continue
        u = urlparse(ln)
        q = parse_qs(u.query)
        rows.append(
            {
                "uuid": u.username,
                "host": u.hostname,
                "port": u.port or 443,
                "sni": q.get("sni", [""])[0],
                "pbk": q.get("pbk", [""])[0],
                "fp": q.get("fp", ["chrome"])[0],
                "flow": q.get("flow", ["xtls-rprx-vision"])[0],
                "sid": q.get("sid", [""])[0],
                "spx": q.get("spx", ["/"])[0],
                "label": unquote(u.fragment),
            }
        )
    return rows


def ordered(rows: list[dict]) -> list[dict]:
    cands = [r for r in rows if r.get("pbk") and not any(e in r["label"] for e in EXCLUDE)]
    if os.path.exists(PREF_FILE):
        pin = open(PREF_FILE).read().strip()
        if pin:
            pinned = [r for r in cands if pin in r["label"]]
            return pinned + [r for r in cands if r not in pinned]

    def rank(r: dict) -> int:
        for i, key in enumerate(PREF):
            if key in r["label"]:
                return i
        return len(PREF)

    return sorted(cands, key=rank)


def cfg_for(row: dict, *, socks_port: int = 1080, http_port: int = 1081) -> dict:
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "socks-in",
                "listen": "0.0.0.0",
                "port": socks_port,
                "protocol": "socks",
                "settings": {"auth": "noauth", "udp": True},
            },
            {
                "tag": "http-in",
                "listen": "0.0.0.0",
                "port": http_port,
                "protocol": "http",
                "settings": {},
            },
        ],
        "outbounds": [
            {
                "tag": "proxy",
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": row["host"],
                            "port": int(row["port"]),
                            "users": [
                                {
                                    "id": row["uuid"],
                                    "encryption": "none",
                                    "flow": row["flow"] or "xtls-rprx-vision",
                                }
                            ],
                        }
                    ]
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "serverName": row["sni"],
                        "fingerprint": row["fp"] or "chrome",
                        "publicKey": row["pbk"],
                        "shortId": row["sid"] or "",
                        "spiderX": row["spx"] or "/",
                    },
                },
            }
        ],
    }


def dc_via(proxy_url: str) -> bool:
    try:
        t = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                NET,
                "-e",
                "DST=" + DC_HOST,
                "-e",
                "DPORT=" + DC_PORT,
                "-e",
                "PROXY=" + proxy_url,
                PROBE_IMAGE,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return t.returncode == 0
    except Exception as e:
        log("probe-run error " + str(e))
        return False


def probe_candidate(row: dict) -> bool:
    tmp = f"{BASE}/xray-data/_probe.json"
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    with open(tmp, "w") as f:
        json.dump(cfg_for(row), f)
    subprocess.run(["docker", "rm", "-f", "xray-probe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    st = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            "xray-probe",
            "--network",
            NET,
            "-v",
            tmp + ":/etc/xray/config.json:ro",
            XRAY_IMAGE,
            "run",
            "-c",
            "/etc/xray/config.json",
        ],
        capture_output=True,
        text=True,
    )
    if st.returncode != 0:
        log("probe xray start failed: " + st.stderr[:120])
        return False
    time.sleep(4)
    ok = dc_via("socks5://xray-probe:1080")
    subprocess.run(["docker", "rm", "-f", "xray-probe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return ok


def activate(row: dict) -> bool:
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    if os.path.isfile(CONFIG):
        shutil.copy(CONFIG, CONFIG + ".bak")
    with open(CONFIG, "w") as f:
        json.dump(cfg_for(row), f, indent=2)
    subprocess.run(["docker", "restart", "xray"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(5)
    if dc_via("socks5://xray:1080") and dc_via("http://xray:1081"):
        with open(STATE, "w") as f:
            json.dump(
                {
                    "label": row["label"],
                    "host": row["host"],
                    "sni": row["sni"],
                    "activated_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
                f,
                indent=2,
            )
        log("ACTIVATED " + row["label"] + " (" + row["host"] + ")")
        return True
    log("prod verify FAILED for " + row["host"] + " -> rollback")
    bak = CONFIG + ".bak"
    if os.path.isfile(bak):
        shutil.copy(bak, CONFIG)
        subprocess.run(["docker", "restart", "xray"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(5)
    return False


def current_host() -> str | None:
    if not os.path.isfile(CONFIG):
        return None
    try:
        cur = json.load(open(CONFIG))
        return cur["outbounds"][0]["settings"]["vnext"][0]["address"]
    except Exception:
        return None


def main() -> None:
    try:
        rows = fetch_servers()
    except Exception as e:
        log("ERROR fetch failed: " + str(e) + " (keeping current config)")
        sys.exit(1)
    os.makedirs(os.path.dirname(SERVERS), exist_ok=True)
    with open(SERVERS, "w") as f:
        json.dump(rows, f)
    log("net=" + NET + " fetched=" + str(len(rows)) + " servers")
    cands = ordered(rows)
    if not cands:
        log("ERROR no usable candidates (keeping current)")
        sys.exit(2)
    cur_host = current_host()
    hosts = [r["host"] for r in cands]
    if cur_host and cur_host in hosts and dc_via("socks5://xray:1080") and dc_via("http://xray:1081"):
        log("current server " + cur_host + " still healthy -> no change")
        sys.exit(0)
    log("current (" + str(cur_host) + ") unhealthy or rotated out -> selecting new")
    for row in cands:
        log("probe " + row["label"][:26] + " (" + row["host"] + ")")
        if probe_candidate(row) and activate(row):
            sys.exit(0)
    log("ERROR: no working server found across " + str(len(cands)) + " candidates (kept existing)")
    sys.exit(3)


if __name__ == "__main__":
    main()
