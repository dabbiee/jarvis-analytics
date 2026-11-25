"""Crea dashboard_telefono.html: una versione CIFRATA della dashboard da condividere.

Uso (terminale):
    python crea_versione_protetta.py

- Rigenera i dati dai log di Claude Code.
- Ti chiede una password (non viene salvata da nessuna parte).
- Il file contiene i dati cifrati con AES-256-GCM; la chiave deriva dalla password con PBKDF2-SHA256.
  Senza la password la pagina non mostra niente. Scegli una password lunga: e' l'unica protezione.
"""
import base64, getpass, hashlib, json, os, sys
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analizza_token  # noqa: E402

ITER = 310_000
TEMPLATE = (HERE / "dashboard_template.html").read_text(encoding="utf-8")

LOCK_CSS = """
#lock{position:fixed;inset:0;z-index:100;display:flex;align-items:center;justify-content:center;background:var(--bg);padding:20px}
#lock .box{width:min(380px,100%);border:1px solid var(--edge2);background:var(--panel);padding:26px 24px;box-shadow:0 0 30px rgba(200,22,31,.25),0 0 0 1px rgba(245,184,61,.25)}
#lock h1{font-family:var(--disp);font-size:15px;letter-spacing:.2em;margin:0 0 6px;color:var(--gold)}
#lock p{font-size:12px;color:var(--ink2);margin:0 0 16px;line-height:1.5}
#lock input{width:100%;font:inherit;font-size:14px;color:var(--ink);background:rgba(0,0,0,.3);border:1px solid var(--edge2);padding:10px 12px;outline:none}
#lock input:focus{border-color:var(--cy)}
#lock button{margin-top:12px;width:100%;font-family:var(--mono);font-size:13px;letter-spacing:.14em;padding:10px;cursor:pointer;background:linear-gradient(90deg,var(--red),var(--gold));color:#fff;border:0}
#lock .err{color:var(--rd);font-size:12px;margin-top:10px;min-height:16px}
"""

LOCK_HTML = """
<div id="lock"><div class="box">
  <h1>J.A.R.V.I.S. · ACCESSO</h1>
  <p>Protocollo di sicurezza Stark attivo. Inserisci la password per visualizzare i dati.</p>
  <input type="password" id="pw" placeholder="password" autocomplete="off">
  <button id="go">APRI</button>
  <div class="err" id="err"></div>
</div></div>
"""

UNLOCK_JS = """
<script>
const PAYLOAD = __PAYLOAD__;
const b64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
async function sblocca(){
  const err = document.getElementById('err');
  const pw = document.getElementById('pw').value;
  if(!pw){ err.textContent = 'Inserisci la password.'; return; }
  try{
    const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(pw), 'PBKDF2', false, ['deriveKey']);
    const key = await crypto.subtle.deriveKey(
      {name:'PBKDF2', salt: b64(PAYLOAD.salt), iterations: PAYLOAD.iter, hash:'SHA-256'},
      base, {name:'AES-GCM', length:256}, false, ['decrypt']);
    const clear = await crypto.subtle.decrypt({name:'AES-GCM', iv: b64(PAYLOAD.iv)}, key, b64(PAYLOAD.ct));
    window.__D = JSON.parse(new TextDecoder().decode(clear));
  }catch(e){
    err.textContent = 'Password errata.';
    document.getElementById('pw').select();
    return;
  }
  document.getElementById('lock').remove();
  const s = document.createElement('script');
  s.textContent = document.getElementById('app').textContent;
  document.body.appendChild(s);
}
document.getElementById('go').onclick = sblocca;
document.getElementById('pw').addEventListener('keydown', e => { if(e.key === 'Enter') sblocca(); });
document.getElementById('pw').focus();
</script>
"""


def costruisci(data: dict, password: str) -> str:
    data = dict(data, standalone=True)               # niente link agli zip: sul telefono non servono
    clear = json.dumps(data, ensure_ascii=False).encode("utf-8")
    salt, iv = os.urandom(16), os.urandom(12)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITER, dklen=32)
    ct = AESGCM(key).encrypt(iv, clear, None)
    payload = {"salt": base64.b64encode(salt).decode(), "iv": base64.b64encode(iv).decode(),
               "ct": base64.b64encode(ct).decode(), "iter": ITER}

    # Pagina: stile e struttura del template, app spostata in uno <script type="text/plain"> e avviata solo dopo lo sblocco.
    head, rest = TEMPLATE.split("<body>", 1)
    body, script_all = rest.rsplit("<script>", 1)
    app_js, _ = script_all.split("</script>", 1)
    app_js = app_js.replace("const D=/*__DATA__*/null;", "const D=window.__D;")
    head = head.replace("</style>", LOCK_CSS + "</style>")
    head = head.replace('<link rel="icon" href="/*__ICON__*/">', "").replace('<link rel="icon" href="icona.png">', "")
    unlock = UNLOCK_JS.replace("__PAYLOAD__", json.dumps(payload))
    return (head + "<body>" + LOCK_HTML + body +
            '<script type="text/plain" id="app">' + app_js + "</script>" + unlock + "</body></html>")


def main():
    analizza_token.main()
    data = analizza_token.ULTIMI
    p1 = getpass.getpass("Password per la versione condivisa: ")
    p2 = getpass.getpass("Ripeti password: ")
    if p1 != p2:
        raise SystemExit("Le password non coincidono.")
    if len(p1) < 10:
        raise SystemExit("Usa almeno 10 caratteri: e' l'unica protezione del file.")
    out = HERE / "dashboard_telefono.html"
    out.write_text(costruisci(data, p1), encoding="utf-8")
    print(f"Creato {out.name} (cifrato). Puoi condividerlo: senza password non mostra dati.")


if __name__ == "__main__":
    main()
