# Polymarket Bot

Kollaboratives Projekt zur Entwicklung eines ML-basierten Trading-Bots für Polymarket BTC-Märkte.

## Projektstruktur

```
polymarket-bot/
├── person-a/          # Person A's Arbeitsbereich
├── person-b/          # Person B's Arbeitsbereich
│   ├── *.py           # Python Scripts
│   ├── *.csv          # Daten (Chainlink History, Labels)
│   └── docs/          # Dokumentation & Reports
├── shared/            # Gemeinsamer Code (später)
└── README.md
```

## Aktueller Stand

### Daten
- **chainlink_history.csv**: 1.004 Chainlink Oracle Updates (BTC/USD)
- **labeled_data.csv**: Gelabelte Daten für ML (Up=1, Down=0)

### Modell (Person B)
- Logistische Regression mit L2-Regularisierung
- Features: `oracle_lag_pct`, `sigma`, `momentum`
- Walk-Forward Backtest: 2 Folds
- Ergebnis: Brier Score ~0.25 (Baseline-Level)

### Dokumentation
- `docs/model_report.md` - Modell-Evaluation
- `docs/edge_hypothesis.md` - Trading-Hypothese
- `docs/CRITICAL_RULES.md` - Projekt-Regeln

## Setup

```bash
cd person-b
pip install -r requirements.txt
```

## Nächste Schritte
- [ ] Mehr Features entwickeln (Phase A)
- [ ] Mehr historische Daten sammeln
- [ ] Shared utilities extrahieren
