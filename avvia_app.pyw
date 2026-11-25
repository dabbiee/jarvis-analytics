"""Claude Code Analytics: avvia la dashboard come app desktop (finestra Edge senza barra).

Doppio clic (o collegamento sul Desktop): aggiorna i dati e apre la finestra.
Il server resta attivo in background. Nessuna console.

Chi puo' aprire la dashboard (vedi accesso_casa.py per le regole):
- il PC stesso, senza password;
- un dispositivo sul Wi-Fi di casa, con password;
- da fuori casa, solo tramite Tailscale, un dispositivo che e' stato sul Wi-Fi di casa
  da meno di 24 ore, con password. Tutti gli altri vengono rifiutati.
La rete di casa si ricalcola da sola: cambiare modem o casa non richiede modifiche.
"""
import base64, functools, hashlib, hmac, http.server, json, os, socketserver, subprocess, sys, threading, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.chdir(HERE)

import accesso_casa  # noqa: E402

PORT = 8765
ACCESSO = HERE / "accesso.json"

EDGES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

PAGINA_NEGATA = """<!doctype html><html lang="it"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Accesso negato</title>
<body style="margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#0b0f14;color:#eaf0f5;font-family:Consolas,monospace;padding:16px">
<div style="max-width:420px;border:1px solid #33414f;padding:24px;background:#121820">
<h1 style="color:#e0a83a;font-size:16px;letter-spacing:.2em;margin:0 0 10px">J.A.R.V.I.S. · ACCESSO NEGATO</h1>
<p style="color:#bac5d0;font-size:13px;line-height:1.6;margin:0">{motivo}</p></div></body></html>"""


def verifica_password(provata: str) -> bool:
    cfg = json.loads(ACCESSO.read_text(encoding="utf-8"))
    h = hashlib.pbkdf2_hmac("sha256", provata.encode("utf-8"), bytes.fromhex(cfg["sale"]), cfg["iter"])
    return hmac.compare_digest(h.hex(), cfg["hash"])


class Handler(http.server.SimpleHTTPRequestHandler):
    protetto = False

    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _password_ok(self) -> bool:
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            try:
                _, pwd = base64.b64decode(auth[6:]).decode("utf-8").split(":", 1)
                if verifica_password(pwd):
                    return True
            except Exception:
                pass
            time.sleep(1)          # rallenta chi prova password a raffica
        return False

    def _controlla(self) -> bool:
        if not self.protetto:
            return True
        esito, motivo = accesso_casa.valuta(self.client_address[0])
        if esito == "libero":
            return True
        if esito == "no":
            body = PAGINA_NEGATA.format(motivo=motivo).encode("utf-8")
            self.send_response(403)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return False
        if self._password_ok():
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Claude Code Analytics"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def do_GET(self):
        if self._controlla():
            super().do_GET()

    def do_HEAD(self):
        if self._controlla():
            super().do_HEAD()


def avvia_server(host: str, protetto: bool):
    class H(Handler):
        pass
    H.protetto = protetto
    handler = functools.partial(H, directory=str(HERE))
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    srv = socketserver.ThreadingTCPServer((host, PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()


def scrivi_indirizzi():
    righe = [f"A casa (Wi-Fi):   http://{accesso_casa.ip_locale()}:{PORT}/dashboard_token.html"]
    nome = accesso_casa.nome_tailscale()
    if nome:
        righe.append(f"Ovunque (Tailscale acceso sul telefono): http://{nome}:{PORT}/dashboard_token.html")
    else:
        righe.append("Da fuori casa: installa Tailscale su PC e telefono (stesso account), poi riavvia l'app.")
    righe.append("Utente qualsiasi, password impostata con imposta_accesso.py.")
    righe.append("Da fuori funziona solo se il telefono e' stato sul Wi-Fi di casa (con Tailscale acceso) da meno di 24 ore.")
    (HERE / "indirizzo_telefono.txt").write_text("\n".join(righe) + "\n", encoding="utf-8")


def main():
    try:
        import analizza_token
        analizza_token.main()          # dati sempre freschi a ogni avvio
    except Exception as e:
        (HERE / "errore_avvio.log").write_text(repr(e), encoding="utf-8")

    rete = ACCESSO.exists()
    try:
        if rete:
            avvia_server("0.0.0.0", True)      # casa + Tailscale, con le regole di accesso_casa
            accesso_casa.avvia_sorveglianza()  # rinnova il pass dei dispositivi che sono sul Wi-Fi
            scrivi_indirizzi()
        else:
            avvia_server("127.0.0.1", False)   # senza password non esponiamo nulla in rete
    except OSError:
        pass   # porta gia' occupata: un'altra copia del server e' gia' attiva

    url = f"http://127.0.0.1:{PORT}/dashboard_token.html"
    browser = next((p for p in EDGES if os.path.exists(p)), None)
    if not browser:
        import webbrowser
        webbrowser.open(url)
    else:
        profile = HERE / ".profilo_app"
        subprocess.Popen([browser, f"--app={url}", f"--user-data-dir={profile}", "--window-size=1500,950",
                          "--no-first-run", "--disable-features=Translate", "--hide-crash-restore-bubble"])
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
