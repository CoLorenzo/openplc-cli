from __future__ import annotations
import re
import time
import json
import pathlib
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

import httpx
import backoff
from bs4 import BeautifulSoup


@dataclass
class OpenPLCClientConfig:
    base_url: str = "http://localhost:8080"
    timeout_s: float = 20.0
    follow_redirects: bool = True
    user_agent: str = "openplc.py/0.1 (+httpx)"
    # opzionale: file dove salvare i cookie di sessione
    cookie_path: Optional[str] = None
    # headers comuni: Referer/Origin utili per alcune viste
    default_headers: Dict[str, str] = field(default_factory=lambda: {})


class OpenPLCClient:
    def __init__(self, cfg: OpenPLCClientConfig):
        self.cfg = cfg
        self.client = httpx.Client(
            base_url=cfg.base_url,
            timeout=cfg.timeout_s,
            follow_redirects=cfg.follow_redirects,
            headers={
                "User-Agent": cfg.user_agent,
                **(cfg.default_headers or {}),
            },
        )
        # se richiesto, prova a caricare cookie persistiti
        if cfg.cookie_path:
            self._load_cookies(cfg.cookie_path)

    # ---------- utility ----------
    def close(self):
        if self.cfg.cookie_path:
            self._save_cookies(self.cfg.cookie_path)
        self.client.close()

    def _save_cookies(self, path: str):
        jar_dict = {}
        for cookie in self.client.cookies.jar:
            # key univoca: (domain, path, name)
            key = f"{cookie.domain}|{cookie.path}|{cookie.name}"
            jar_dict[key] = {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
                "secure": cookie.secure,
                "expires": cookie.expires,
            }
        pathlib.Path(path).write_text(json.dumps(jar_dict, indent=2))

    def _load_cookies(self, path: str):
        p = pathlib.Path(path)
        if not p.exists():
            return
        data = json.loads(p.read_text())
        for _, c in data.items():
            self.client.cookies.set(
                name=c["name"], value=c["value"], domain=c["domain"], path=c["path"]
            )

    # retry esponenziale su errori rete/timeout
    def _backoff_predicate(exc: Exception) -> bool:
        return isinstance(exc, (httpx.TransportError, httpx.ReadTimeout))

    # ---------- auth ----------
    @backoff.on_exception(backoff.expo, (httpx.HTTPError,), max_tries=3, giveup=_backoff_predicate)
    def login(self, username: str, password: str) -> None:
        """
        Login form-urlencoded (come il tuo curl). Setta i cookie di sessione nel client.
        """
        data = {"username": username, "password": password}
        r = self.client.post("/login", data=data, headers={
            "Content-Type": "application/x-www-form-urlencoded",
        })
        r.raise_for_status()
        # opzionalmente verifica di essere autenticato controllando redirect o una view
        # qui lasciamo semplice, i cookie sono già memorizzati nel client


    # ---------- Status check ----------
    def status(self) -> str:
        """
        Effettua una richiesta GET alla root del server e ritorna 'online' se risponde 302, altrimenti 'offline'.
        """
        try:
            r = self.client.get("/")
            if r.status_code == 302:
                return "online"
            else:
                return "offline"
        except httpx.RequestError:
            return "offline"

    
    # ---------- Modbus: lista + add ----------
    def list_modbus_devices(self) -> List[Dict[str, str]]:
        """
        Effettua GET /modbus e ritorna la tabella come lista di dict (header->valore).
        """
        r = self.client.get("/modbus")
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        table = soup.find("table")
        if table is None:
            return []
        # estrai header
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        rows: List[Dict[str, str]] = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if cells:
                # se header presente e lunghezze combaciano, mappa header->cell
                if headers and len(headers) == len(cells):
                    rows.append({headers[i]: cells[i] for i in range(len(headers))})
                else:
                    # fallback: usa indici come chiavi
                    rows.append({str(i): c for i, c in enumerate(cells)})
        return rows

    def add_modbus_device(
        self,
        *,
        device_name: str,
        device_protocol: str = "TCP",
        device_id: int = 1,
        device_ip: str = "127.0.0.1",
        device_port: int = 502,
        device_cport: str = "/dev/ttyS0",
        device_baud: int = 115200,
        device_parity: str = "None",
        device_data: int = 8,
        device_stop: int = 1,
        device_pause: int = 0,
        di_start: int = 0,
        di_size: int = 8,
        do_start: int = 0,
        do_size: int = 8,
        ai_start: int = 0,
        ai_size: int = 8,
        aor_start: int = 0,
        aor_size: int = 8,
        aow_start: int = 0,
        aow_size: int = 8,
    ) -> None:
        """
        Replica il tuo POST multipart a /add-modbus-device.
        """
        data = {
            "device_name": device_name,
            "device_protocol": device_protocol,
            "device_id": str(device_id),
            "device_ip": device_ip,
            "device_port": str(device_port),
            "device_cport": device_cport,
            "device_baud": str(device_baud),
            "device_parity": device_parity,
            "device_data": str(device_data),
            "device_stop": str(device_stop),
            "device_pause": str(device_pause),
            "di_start": str(di_start),
            "di_size": str(di_size),
            "do_start": str(do_start),
            "do_size": str(do_size),
            "ai_start": str(ai_start),
            "ai_size": str(ai_size),
            "aor_start": str(aor_start),
            "aor_size": str(aor_size),
            "aow_start": str(aow_start),
            "aow_size": str(aow_size),
        }
        # httpx fa automaticamente multipart se usi 'files' o 'data'; per sicurezza usiamo 'files'
        files = [(k, (None, v)) for k, v in data.items()]
        r = self.client.post("/add-modbus-device", files=files, headers={"Referer": f"{self.cfg.base_url}/modbus"})
        r.raise_for_status()

    # ---------- Programmi: lista ----------
    def list_programs(self) -> List[Dict[str, str]]:
        """
        GET /programs -> parse tabella come lista di dict.
        """
        r = self.client.get("/programs")
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        table = soup.find("table")
        if table is None:
            return []
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        rows: List[Dict[str, str]] = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if cells:
                if headers and len(headers) == len(cells):
                    rows.append({headers[i]: cells[i] for i in range(len(headers))})
                else:
                    rows.append({str(i): c for i, c in enumerate(cells)})
        return rows

    # ---------- Upload programma: step1 upload file, step2 action ----------
    def _parse_upload_response(self, html: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Estrae prog_file ed epoch_time dalla risposta HTML di /upload-program.
        Fallback: cerca pattern '[0-9]+.st'.
        """
        soup = BeautifulSoup(html, "lxml")
        def find_input(name: str) -> Optional[str]:
            el = soup.find("input", {"name": name})
            return el.get("value") if el else None

        prog_file = find_input("prog_file")
        epoch_time = find_input("epoch_time")

        if not prog_file:
            # fallback regex tipo bash
            m = re.search(r"(\d+\.st)", html)
            if m:
                prog_file = m.group(1)
        return prog_file, epoch_time

    def upload_program(self, file_path: str | pathlib.Path, prog_name: str, prog_descr: str) -> Dict[str, Any]:
        """
        Esegue:
          1) POST /upload-program (multipart file) -> parse prog_file, epoch_time
          2) POST /upload-program-action con i metadati
        Ritorna un dict con info di esito.
        """
        fp = pathlib.Path(file_path)
        if not fp.is_file():
            raise FileNotFoundError(fp)

        # STEP 1: upload del file
        files = {"file": (fp.name, fp.read_bytes(), "text/plain")}
        r1 = self.client.post(
            "/upload-program",
            files=files,
            headers={
                "Referer": f"{self.cfg.base_url}/upload-program",
                "Origin": self.cfg.base_url,
            },
        )
        r1.raise_for_status()
        prog_file, epoch_time = self._parse_upload_response(r1.text)

        if not prog_file:
            # diagnostica: restituisci snippet della pagina
            snippet = r1.text[:800]
            raise RuntimeError(f"Impossibile estrarre 'prog_file' dalla risposta HTML. Snippet:\n{snippet}")

        if not epoch_time:
            epoch_time = str(int(time.time()))

        # STEP 2: registrazione metadati
        data = {
            "prog_name": prog_name,
            "prog_descr": prog_descr,
            "prog_file": prog_file,
            "epoch_time": epoch_time,
        }
        # usa multipart form (come nel tuo curl)
        files2 = [(k, (None, v)) for k, v in data.items()]
        r2 = self.client.post(
            "/upload-program-action",
            files=files2,
            headers={
                "Referer": f"{self.cfg.base_url}/upload-program",
                "Origin": self.cfg.base_url,
            },
        )
        # Alcune build rispondono 302->/programs: seguiamo già i redirect
        if r2.status_code not in (200, 302):
            raise httpx.HTTPStatusError(
                f"upload-program-action HTTP {r2.status_code}", request=r2.request, response=r2
            )
        return {
            "status": "ok",
            "prog_file": prog_file,
            "epoch_time": epoch_time,
            "http_status": r2.status_code,
        }

    # ---------- Program management ----------
    def remove_program(self, prog_id: int) -> None:
        r = self.client.get(f"/remove-program?id={prog_id}")
        r.raise_for_status()

    # ---------- PLC runtime ----------
    def start_plc(self) -> None:
        r = self.client.get("/start_plc")
        r.raise_for_status()

    def stop_plc(self) -> None:
        r = self.client.get("/stop_plc")
        r.raise_for_status()

    def runtime_logs(self) -> str:
        r = self.client.get("/runtime_logs")
        r.raise_for_status()
        return r.text


# ------------- Esempio d'uso CLI veloce -------------
if __name__ == "__main__":
    import argparse, sys

    ap = argparse.ArgumentParser(description="OpenPLC httpx client (demo)")
    ap.add_argument("--host", default="http://localhost:8080")
    ap.add_argument("--cookie", default="/tmp/openplc_cookies.json")
    ap.add_argument("--user", default="openplc")
    ap.add_argument("--pass", dest="password", default="openplc")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login")
    sub.add_parser("modbus-list")
    p_add = sub.add_parser("modbus-add")
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--ip", required=True)
    p_add.add_argument("--port", type=int, default=502)
    p_add.add_argument("--id", type=int, default=1)
    sub.add_parser("programs")
    p_up = sub.add_parser("upload")
    p_up.add_argument("--file", required=True)
    p_up.add_argument("--name", required=True)
    p_up.add_argument("--descr", default="")
    p_rm = sub.add_parser("remove")
    p_rm.add_argument("--id", type=int, required=True)
    sub.add_parser("start")
    sub.add_parser("stop")
    sub.add_parser("logs")
    sub.add_parser("status")


    args = ap.parse_args()

    cfg = OpenPLCClientConfig(
        base_url=args.host,
        cookie_path=args.cookie,
        default_headers={"Referer": args.host, "Origin": args.host},
    )
    cli = OpenPLCClient(cfg)

    try:
        if args.cmd == "login":
            cli.login(args.user, args.password)
            print("Login OK")
        elif args.cmd == "modbus-list":
            for row in cli.list_modbus_devices():
                print(row)
        elif args.cmd == "modbus-add":
            cli.add_modbus_device(
                device_name=args.name,
                device_ip=args.ip,
                device_port=args.port,
                device_id=args.id,
            )
            print("Modbus device aggiunto.")
        elif args.cmd == "programs":
            for row in cli.list_programs():
                print(row)
        elif args.cmd == "upload":
            info = cli.upload_program(args.file, args.name, args.descr)
            print(json.dumps(info, indent=2))
        elif args.cmd == "remove":
            cli.remove_program(args.id)
            print("Programma rimosso.")
        elif args.cmd == "start":
            cli.start_plc()
            print("PLC avviato.")
        elif args.cmd == "stop":
            cli.stop_plc()
            print("PLC stoppato.")
        elif args.cmd == "logs":
            print(cli.runtime_logs())
        elif args.cmd == "status":
            print(cli.status())
    finally:
        cli.close()

