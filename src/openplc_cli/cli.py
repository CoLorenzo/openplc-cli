#!/usr/bin/env python3
# openplc-cli.py
from __future__ import annotations

import sys
import os
import json
import argparse
from pathlib import Path
import time
from typing import Any, Dict, List
from getpass import getpass

from .pyopenplc import OpenPLCClient, OpenPLCClientConfig


# ========= Stato persistente =========

def _state_dir() -> Path:
    cfg = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    d = Path(cfg) / "openplc-cli"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _state_path() -> Path:
    return _state_dir() / "session.json"

def _load_state() -> Dict[str, str]:
    p = _state_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}

def _save_state(host: str, cookie: str) -> None:
    data = {"host": host, "cookie": cookie}
    _state_path().write_text(json.dumps(data, indent=2))

def _sanitize_host_for_filename(host: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in host.strip())

def _default_cookie_for_host(host: str) -> str:
    cache_root = os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
    d = Path(cache_root) / "openplc-cli"
    d.mkdir(parents=True, exist_ok=True)
    return str(d / f"cookies-{_sanitize_host_for_filename(host)}.json")


# ========= Utility CLI =========

def add_global_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--host",
                    help="Base URL OpenPLC (se omesso: ultimo login o default http://localhost:8080)")
    ap.add_argument("--cookie",
                    help="Percorso file cookie (se omesso: ultimo login o cache per host)")
    ap.add_argument("--timeout", type=float, default=20.0,
                    help="Timeout HTTP in secondi (default: %(default)s)")
    ap.add_argument("--json", action="store_true",
                    help="Output JSON, se applicabile")

def print_table(rows: List[Dict[str, Any]]) -> None:
    if not rows:
        print("(vuoto)")
        return
    keys: List[str] = []
    for r in rows:
        for k in r.keys():
            if k not in keys:
                keys.append(k)
    widths = {k: max(len(str(k)), *(len(str(r.get(k, ""))) for r in rows)) for k in keys}
    header = "  ".join(f"{k:{widths[k]}}" for k in keys)
    sep = "  ".join("-" * widths[k] for k in keys)
    print(header)
    print(sep)
    for r in rows:
        print("  ".join(f"{str(r.get(k, '')):{widths[k]}}" for k in keys))

def with_client(args: argparse.Namespace, fn):
    cfg = OpenPLCClientConfig(
        base_url=args.host,
        cookie_path=args.cookie,
        follow_redirects=False,
        timeout_s=args.timeout,
        default_headers={"Referer": args.host, "Origin": args.host},
    )
    client = OpenPLCClient(cfg)
    try:
        return fn(client)
    finally:
        client.close()


# ========= Comandi =========

def cmd_login(args: argparse.Namespace) -> int:
    host = args.addr.rstrip("/")
    cookie = args.cookie or _default_cookie_for_host(host)

    username = args.user or input("Username: ").strip()
    password = args.password or getpass("Password: ")

    def run(client: OpenPLCClient):
        client.login(username, password)
        print("Login OK")
        _save_state(host, cookie)

    args.host = host
    args.cookie = cookie
    return with_client(args, run) or 0


def cmd_device_ls(args: argparse.Namespace) -> int:
    def run(client: OpenPLCClient):
        rows = client.list_modbus_devices()
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
        else:
            print_table(rows)
    return with_client(args, run) or 0


def cmd_device_create(args: argparse.Namespace) -> int:
    def run(client: OpenPLCClient):
        client.add_modbus_device(
            device_name=args.name,
            device_protocol=args.protocol,
            device_id=args.id,
            device_ip=args.ip,
            device_port=args.port,
            device_cport=args.cport,
            device_baud=args.baud,
            device_parity=args.parity,
            device_data=args.databits,
            device_stop=args.stopbits,
            device_pause=args.pause,
            di_start=args.di_start,
            di_size=args.di_size,
            do_start=args.do_start,
            do_size=args.do_size,
            ai_start=args.ai_start,
            ai_size=args.ai_size,
            aor_start=args.aor_start,
            aor_size=args.aor_size,
            aow_start=args.aow_start,
            aow_size=args.aow_size,
        )
        print("Dispositivo Modbus creato.")
    return with_client(args, run) or 0


def cmd_program_ls(args: argparse.Namespace) -> int:
    def run(client: OpenPLCClient):
        rows = client.list_programs()
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
        else:
            print_table(rows)
    return with_client(args, run) or 0


def cmd_program_create(args: argparse.Namespace) -> int:
    def run(client: OpenPLCClient):
        info = client.upload_program(args.file, args.name, args.descr)
        print(json.dumps(info, indent=2, ensure_ascii=False))
    return with_client(args, run) or 0


def cmd_plc_start(args: argparse.Namespace) -> int:
    def run(client: OpenPLCClient):
        client.start_plc()
        print("PLC avviato.")
    return with_client(args, run) or 0


def cmd_plc_stop(args: argparse.Namespace) -> int:
    def run(client: OpenPLCClient):
        client.stop_plc()
        print("PLC stoppato.")
    return with_client(args, run) or 0

def cmd_status(args: argparse.Namespace) -> int:
    def run(client: OpenPLCClient):
        print(f"DEBUG: cmd_status - client base_url: {client.cfg.base_url}")
        s = client.status()  # ritorna "online" oppure "offline"
        if args.json:
            print(json.dumps({"status": s}, indent=2, ensure_ascii=False))
        else:
            print(s)
    return with_client(args, run) or 0


def cmd_status_onlinewait(args: argparse.Namespace) -> int:
    def run(client: OpenPLCClient):
        print(f"Waiting for OpenPLC server at {client.cfg.base_url} to come online...")
        while True:
            try:
                status = client.status()
                if status == "online":
                    print(f"OpenPLC server at {client.cfg.base_url} is online.")
                    break
                else:
                    print(f"Server status: {status}. Retrying in 5 seconds...")
            except Exception as e:
                print(f"Error checking server status: {e}. Retrying in 5 seconds...")
            time.sleep(5)
    return with_client(args, run) or 0


# ========= Parser =========

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="openplc-cli",
        description="CLI per OpenPLC basata su httpx (con stato persistente host/cookie)",
    )
    add_global_args(ap)
    sub = ap.add_subparsers(dest="cmd", required=True)

    # login
    p_login = sub.add_parser("login", help="Esegue login (salva host/cookie)")
    p_login.add_argument("-a", "--addr", required=True, help="Base URL (es: http://localhost:8080)")
    p_login.add_argument("-u", "--user", help="Username (se omesso, richiesto interattivamente)")
    p_login.add_argument("-p", "--password", help="Password (se omessa, richiesta interattivamente)")
    p_login.add_argument("--cookie", help="File cookie (se omesso, generato per host)")
    p_login.set_defaults(func=cmd_login)

    # device
    p_dev = sub.add_parser("device", help="Gestione Modbus devices")
    sub_dev = p_dev.add_subparsers(dest="device_cmd", required=True)

    p_dev_ls = sub_dev.add_parser("ls", help="Lista slave devices")
    add_global_args(p_dev_ls)
    p_dev_ls.set_defaults(func=cmd_device_ls)

    p_dev_create = sub_dev.add_parser("create", help="Crea uno slave device")
    p_dev_create.add_argument("--name", required=True, help="Nome dispositivo (es: Conveyor)")
    p_dev_create.add_argument("--protocol", default="TCP", choices=["TCP", "RTU"], help="Protocollo")
    p_dev_create.add_argument("--id", type=int, default=1, help="Device ID")
    p_dev_create.add_argument("--ip", default="127.0.0.1", help="IP host Modbus TCP")
    p_dev_create.add_argument("--port", type=int, default=502, help="Porta TCP")
    p_dev_create.add_argument("--cport", default="/dev/ttyS0", help="Serial/COM port per RTU")
    p_dev_create.add_argument("--baud", type=int, default=115200, help="Baud rate")
    p_dev_create.add_argument("--parity", default="None", choices=["None", "Even", "Odd"], help="Parity")
    p_dev_create.add_argument("--databits", type=int, default=8, help="Data bits")
    p_dev_create.add_argument("--stopbits", type=int, default=1, help="Stop bits")
    p_dev_create.add_argument("--pause", type=int, default=0, help="Pausa (ms) tra richieste")
    p_dev_create.add_argument("--di-start", type=int, default=0)
    p_dev_create.add_argument("--di-size", type=int, default=8)
    p_dev_create.add_argument("--do-start", type=int, default=0)
    p_dev_create.add_argument("--do-size", type=int, default=8)
    p_dev_create.add_argument("--ai-start", type=int, default=0)
    p_dev_create.add_argument("--ai-size", type=int, default=8)
    p_dev_create.add_argument("--aor-start", type=int, default=0)
    p_dev_create.add_argument("--aor-size", type=int, default=8)
    p_dev_create.add_argument("--aow-start", type=int, default=0)
    p_dev_create.add_argument("--aow-size", type=int, default=8)
    add_global_args(p_dev_create)
    p_dev_create.set_defaults(func=cmd_device_create)

    # program
    p_prog = sub.add_parser("program", help="Gestione programmi")
    sub_prog = p_prog.add_subparsers(dest="program_cmd", required=True)

    p_prog_ls = sub_prog.add_parser("ls", help="Lista programmi")
    add_global_args(p_prog_ls)
    p_prog_ls.set_defaults(func=cmd_program_ls)

    p_prog_create = sub_prog.add_parser("create", help="Carica un programma")
    p_prog_create.add_argument("--file", required=True, help="Percorso file .st")
    p_prog_create.add_argument("--name", required=True, help="Nome programma")
    p_prog_create.add_argument("--descr", default="", help="Descrizione")
    add_global_args(p_prog_create)
    p_prog_create.set_defaults(func=cmd_program_create)

    # plc
    p_plc = sub.add_parser("plc", help="Controllo PLC runtime")
    sub_plc = p_plc.add_subparsers(dest="plc_cmd", required=True)

    p_plc_start = sub_plc.add_parser("start", help="Avvio PLC")
    add_global_args(p_plc_start)
    p_plc_start.set_defaults(func=cmd_plc_start)

    p_plc_stop = sub_plc.add_parser("stop", help="Stop PLC")
    add_global_args(p_plc_stop)
    p_plc_stop.set_defaults(func=cmd_plc_stop)

    # status
    p_status = sub.add_parser("status", help="Verifica stato dell'istanza (online/offline via HTTP 302 sulla root)")
    sub_status = p_status.add_subparsers(dest="status_cmd", required=True)

    p_status_check = sub_status.add_parser("check", help="Verifica stato corrente")
    add_global_args(p_status_check)
    p_status_check.set_defaults(func=cmd_status)

    p_status_onlinewait = sub_status.add_parser("onlinewait", help="Attende che il server OpenPLC sia online")
    add_global_args(p_status_onlinewait)
    p_status_onlinewait.set_defaults(func=cmd_status_onlinewait)


    return ap


def _resolve_defaults(args: argparse.Namespace) -> None:
    st = _load_state()
    print(f"DEBUG: _resolve_defaults - args.host before state: {getattr(args, "host", None)}")
    if not getattr(args, "host", None):
        args.host = st.get("host", "http://localhost:8080")
    print(f"DEBUG: _resolve_defaults - args.host after state: {args.host}")
    if not getattr(args, "cookie", None):
        args.cookie = st.get("cookie") if st.get("host") == args.host else None
    if not args.cookie:
        args.cookie = _default_cookie_for_host(args.host)


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd != "login":
        _resolve_defaults(args)

    if not hasattr(args, "timeout"):
        args.timeout = 20.0
    if not hasattr(args, "json"):
        args.json = False

    try:
        return args.func(args) or 0
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"Errore: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
