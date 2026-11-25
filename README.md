# Jarvis Analytics

Dashboard in stile J.A.R.V.I.S. per vedere come usi **Claude Code**: token consumati, sessioni, progetti, strumenti, server MCP, skill, subagent e mod.

Funziona **solo con i tuoi dati**: legge i transcript che Claude Code salva sul tuo PC (`~/.claude/projects`) e genera la dashboard in locale. Nel repository non c'è nessun dato: la pagina generata (`dashboard_token.html`), la password e la configurazione personale sono in `.gitignore`.

## Requisiti

- Windows con Python 3.10+ (lo script di analisi gira anche su macOS e Linux)
- Claude Code già usato almeno una volta (servono i file in `~/.claude/projects`)
- Microsoft Edge o Google Chrome per la finestra "app" (altrimenti si apre il browser predefinito)

## Avvio rapido

```powershell
git clone https://github.com/<utente>/jarvis-analytics.git
cd jarvis-analytics
python analizza_token.py --open
```

Per usarla come app desktop: doppio clic su `avvia_app.pyw` (o crea un collegamento sul Desktop con `icona.ico`). Aggiorna i dati, avvia un server locale sulla porta 8765 e apre una finestra senza barra.

## Configurazione (facoltativa)

Copia `config.example.json` come `config.json`:

| Voce | A cosa serve |
|---|---|
| `progetti` | Rinomina o raggruppa i progetti: se il percorso contiene la chiave, il progetto prende quel nome |
| `cartelle_radice` | Usa come nome la sottocartella subito sotto una di queste (es. `Progetti\Tesi\...` → `Tesi`) |
| `nomi_mcp` | Nomi leggibili per i connettori di claude.ai, che compaiono con un UUID diverso per ogni account (prime 8 cifre → nome) |
| `data_confronto` | Attiva lo "Studio ottimizzazione token": confronta il consumo prima e dopo questa data |
| `descrizione_confronto` | Cosa è cambiato in quella data (compare nelle tappe) |

## Aprirla dal telefono (facoltativo)

1. `python imposta_accesso.py` per scegliere una password (si salva solo un hash in `accesso.json`).
2. Riavvia l'app: il file `indirizzo_telefono.txt` contiene l'indirizzo da aprire sul Wi-Fi di casa.
3. Da fuori casa serve [Tailscale](https://tailscale.com) su PC e telefono; l'accesso esterno vale solo per dispositivi passati dal Wi-Fi di casa nelle ultime 24 ore.

Senza `accesso.json` il server ascolta solo su `127.0.0.1`.

## Versione cifrata da condividere

```powershell
pip install -r requirements.txt
python crea_versione_protetta.py
```

Crea `dashboard_telefono.html` con i dati cifrati (AES-256-GCM, chiave da password con PBKDF2). Senza password la pagina non mostra nulla.

## File

| File | Cosa fa |
|---|---|
| `analizza_token.py` | Legge i transcript e le mod in `~/.claude`, genera `dashboard_token.html` e gli zip delle mod in `condivisioni/` |
| `dashboard_template.html` | Grafica HUD (canvas, nessuna libreria; font da Google Fonts). Lo script ci inserisce i dati |
| `avvia_app.pyw` | Launcher: aggiorna i dati, server locale, finestra app |
| `accesso_casa.py` | Regole di accesso da rete di casa e Tailscale |
| `imposta_accesso.py` | Imposta la password per gli altri dispositivi |
| `crea_versione_protetta.py` | Esporta la versione cifrata |

## Privacy

I dati non lasciano il tuo PC. La dashboard generata contiene i titoli delle tue chat e i nomi delle cartelle: non caricarla su GitHub (è già esclusa da `.gitignore`).

## Licenza

MIT
