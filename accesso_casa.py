"""Regole di accesso alla dashboard: casa, Tailscale e pass di 24 ore.

- Rete di casa: la /24 dell'indirizzo locale del PC, ricalcolata ogni minuto.
  Cambiare modem (es. TIM -> Fritz!Box, 192.168.1.x -> 192.168.178.x) o casa non richiede modifiche.
- Da fuori si entra solo con Tailscale (indirizzi 100.64.0.0/10). Tailscale garantisce quale
  dispositivo sta chiamando: l'indirizzo e' legato alla chiave del dispositivo e non si falsifica.
- Un dispositivo Tailscale "e' a casa" quando il PC lo raggiunge direttamente su un indirizzo
  della rete di casa. Ogni volta che succede si rinnova il suo pass: da fuori funziona per 24 ore.
- In dispositivi.json c'e' l'ultima volta che ogni dispositivo e' stato visto a casa.
"""
import ipaddress, json, os, shutil, socket, subprocess, threading, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATO = HERE / "dispositivi.json"
VALIDITA = 24 * 3600
TAILNET = ipaddress.ip_network("100.64.0.0/10")
LOCALI = {"127.0.0.1", "::1"}

_lock = threading.Lock()
_cache = {"rete": (0.0, None), "ts": (0.0, None)}


# ---------- rete di casa ----------
def ip_locale() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.168.0.1", 80))   # UDP: nessun pacchetto inviato, serve solo a sapere l'interfaccia
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def rete_casa():
    t, rete = _cache["rete"]
    if time.time() - t > 60 or rete is None:
        ip = ipaddress.ip_address(ip_locale())
        rete = ipaddress.ip_network(f"{ip}/24", strict=False) if ip.is_private and ip not in TAILNET and not ip.is_loopback else None
        _cache["rete"] = (time.time(), rete)
    return rete


def in_casa(ip: str) -> bool:
    rete = rete_casa()
    try:
        return rete is not None and ipaddress.ip_address(ip) in rete
    except ValueError:
        return False


# ---------- Tailscale ----------
def _tailscale_exe():
    for p in (shutil.which("tailscale"), r"C:\Program Files\Tailscale\tailscale.exe"):
        if p and os.path.exists(p):
            return p
    return None


def stato_tailscale():
    """JSON di 'tailscale status', in cache per 10 secondi. None se Tailscale non c'e' o e' spento."""
    t, dati = _cache["ts"]
    if time.time() - t < 10:
        return dati
    dati = None
    exe = _tailscale_exe()
    if exe:
        try:
            out = subprocess.run([exe, "status", "--json"], capture_output=True, timeout=8,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if out.returncode == 0:
                dati = json.loads(out.stdout.decode("utf-8", "replace"))
        except Exception:
            dati = None
    _cache["ts"] = (time.time(), dati)
    return dati


def nome_tailscale():
    dati = stato_tailscale()
    if not dati or not dati.get("Self"):
        return None
    dns = (dati["Self"].get("DNSName") or "").rstrip(".")
    return dns or (dati["Self"].get("TailscaleIPs") or [None])[0]


def _peer_da_ip(dati, ip):
    for peer in (dati.get("Peer") or {}).values():
        if ip in (peer.get("TailscaleIPs") or []):
            return peer
    return None


def _peer_a_casa(peer) -> bool:
    cur = peer.get("CurAddr") or ""          # es. "192.168.1.30:41641" se collegato direttamente in LAN
    host = cur.rsplit(":", 1)[0].strip("[]") if cur else ""
    return bool(host) and in_casa(host)


# ---------- pass di 24 ore ----------
def _leggi():
    try:
        return json.loads(STATO.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _segna_a_casa(peer):
    with _lock:
        stato = _leggi()
        stato[peer["ID"]] = {"nome": peer.get("HostName", "?"), "ultima_casa": int(time.time())}
        STATO.write_text(json.dumps(stato, indent=1, ensure_ascii=False), encoding="utf-8")


def _ultima_casa(peer) -> int:
    return int(_leggi().get(peer.get("ID"), {}).get("ultima_casa", 0))


def aggiorna_pass():
    """Rinnova il pass di ogni dispositivo Tailscale che in questo momento e' sul Wi-Fi di casa."""
    dati = stato_tailscale()
    if not dati:
        return
    for peer in (dati.get("Peer") or {}).values():
        if peer.get("ID") and _peer_a_casa(peer):
            _segna_a_casa(peer)


def avvia_sorveglianza():
    def giro():
        while True:
            try:
                aggiorna_pass()
            except Exception:
                pass
            time.sleep(60)
    threading.Thread(target=giro, daemon=True).start()


# ---------- decisione ----------
def valuta(ip: str):
    """Restituisce ("libero" | "password" | "no", motivo)."""
    if ip in LOCALI:
        return "libero", ""
    if in_casa(ip):
        dati = stato_tailscale()          # se e' anche un dispositivo Tailscale, gli rinnova il pass
        if dati:
            for peer in (dati.get("Peer") or {}).values():
                cur = (peer.get("CurAddr") or "").rsplit(":", 1)[0].strip("[]")
                if cur == ip and peer.get("ID"):
                    _segna_a_casa(peer)
        return "password", ""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return "no", "Indirizzo non valido."
    if addr not in TAILNET:
        return "no", "La dashboard si apre solo dalla rete di casa o tramite Tailscale."
    dati = stato_tailscale()
    if not dati:
        return "no", "Tailscale non risulta attivo sul PC."
    if ip in (dati.get("Self", {}).get("TailscaleIPs") or []):
        return "password", ""
    peer = _peer_da_ip(dati, ip)
    if not peer or not peer.get("ID"):
        return "no", "Dispositivo sconosciuto."
    if _peer_a_casa(peer):
        _segna_a_casa(peer)
        return "password", ""
    ultima = _ultima_casa(peer)
    if ultima and time.time() - ultima < VALIDITA:
        return "password", ""
    if ultima:
        ore = int((time.time() - ultima) // 3600)
        return "no", (f"Questo dispositivo non e' sul Wi-Fi di casa da {ore} ore (il limite e' 24). "
                      "Collegati al Wi-Fi di casa con Tailscale acceso e riprova da fuori.")
    return "no", ("Questo dispositivo non e' mai stato sul Wi-Fi di casa con Tailscale acceso. "
                  "Collegalo al Wi-Fi di casa almeno una volta e riprova.")
