# Pronostici Calcio (aggiornamento automatico)

Ogni giorno GitHub Actions scarica risultati e calendari reali da football-data.co.uk,
calcola le probabilità e ripubblica la pagina `docs/index.html`.

## Attivazione (una volta sola)
1. Crea un repository su GitHub e carica tutti questi file (mantieni le cartelle `.github` e `docs`).
2. Settings → Pages → Source: "Deploy from a branch" → branch `main`, cartella `/docs`.
3. Actions → "Aggiorna pronostici" → Run workflow (poi va da solo ogni giorno).
4. Il sito sarà su `https://TUO-NOME.github.io/NOME-REPO/`.

## Note
- Le quote usate per "il valore" sono la media dei bookmaker di football-data.co.uk, non Eurobet.
  Per questo la pagina mostra anche "gioca da @X": la quota minima da cercare su Eurobet.
- Campionati coperti: quelli di football-data.co.uk (Inghilterra 4 divisioni, Spagna 2, Italia 2,
  Germania 2, Francia 2, Paesi Bassi, Belgio, Portogallo, Turchia, Grecia, Scozia 4).
- Gli orari del file sono UK e vengono convertiti in ora italiana.

## Backtest (temporaneo)
Actions → "Backtest (temporaneo)" → Run workflow. Dopo qualche minuto il report è su
`https://TUO-NOME.github.io/NOME-REPO/backtest.html`.
Per eliminarlo: cancella `backtest.py`, `.github/workflows/backtest.yml` e `docs/backtest.html`.
