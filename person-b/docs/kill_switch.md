# Kill-Switch Protokoll

Dieses Dokument definiert die verbindlichen Bedingungen, unter denen das Trading sofort gestoppt wird. Beide Teammitglieder müssen dieses Protokoll unterschreiben, bevor Live Trading beginnt.

---

## 1. Kill-Switch Bedingungen

### 1.1 Win Rate Kollaps

| Aspekt | Definition |
|--------|------------|
| **Bedingung** | Win Rate < 52% nach mindestens 50 Trades |
| **Messung** | Rollende 50-Trade Berechnung aus `trades.csv` via `trade_statistics.py` |
| **Frequenz** | Nach jedem Trade automatisch geprüft |
| **Entscheider** | Person B (Strategy) |
| **Aktion** | Trading-Pause, Root-Cause Analyse durchführen |

**Rationale:** 52% liegt ~1% über Break-Even (bei Avg Ask ~0.51). Unter diesem Wert ist profitables Trading nicht mehr gewährleistet.

---

### 1.2 Modell-Dekalibrierung

| Aspekt | Definition |
|--------|------------|
| **Bedingung** | Brier Score > 0.24 für 14 aufeinanderfolgende Tage |
| **Messung** | Täglicher Brier Score aus `trade_statistics.py`, Log in `docs/brier_log.csv` |
| **Frequenz** | Täglich um 00:00 UTC |
| **Entscheider** | Person B (Strategy) |
| **Aktion** | Modell-Retraining mit neuen Daten, falls erfolglos: Projektende |

**Rationale:** Brier Score > 0.24 bedeutet, dass das Modell nicht besser als Zufall ist. Zwei Wochen gibt genug Zeit für natürliche Varianz.

---

### 1.3 Kapital-Drawdown

| Aspekt | Definition |
|--------|------------|
| **Bedingung** | Drawdown > 20% des Startkapitals ($20 von $100) |
| **Messung** | Equity Curve aus `trades.csv`, Peak-to-Trough Berechnung |
| **Frequenz** | Nach jedem Trade automatisch geprüft |
| **Entscheider** | **Automatisch (Hard Stop)** — keine manuelle Übersteuerung möglich |
| **Aktion** | Sofortiger Trading-Stopp, beide Personen analysieren gemeinsam |

**Rationale:** 20% Drawdown ist der absolute Worst-Case. Bei $100 Startkapital bedeutet das $20 Verlust — danach ist Erholung sehr schwierig.

**Eskalation:**
- 8% Drawdown ($8): Warnung, reduzierte Stake-Size
- 15% Drawdown ($15): Kritisch, nur noch 1% Stakes
- 20% Drawdown ($20): **HARD STOP**

---

### 1.4 Technischer Ausfall

| Aspekt | Definition |
|--------|------------|
| **Bedingung** | System offline oder nicht funktionsfähig > 24 Stunden |
| **Messung** | Heartbeat-Log von Person A Infrastructure (`person-a/logs/heartbeat.log`) |
| **Frequenz** | Kontinuierlich, Alarm bei 1h Ausfall |
| **Entscheider** | Person A (Infrastruktur) |
| **Aktion** | Fix innerhalb 24h oder Projektpause bis gelöst |

**Was zählt als Ausfall:**
- Oracle Monitor nicht erreichbar
- Daten-Pipeline liefert keine Updates
- API-Verbindungen (Binance, Polymarket) unterbrochen
- Server/VM nicht erreichbar

---

### 1.5 Edge Verschwunden

| Aspekt | Definition |
|--------|------------|
| **Bedingung** | Oracle Lag < 0.35% für 7 aufeinanderfolgende Tage |
| **Messung** | Statistik aus `person-a/lag_monitor.py`, Daily Summary |
| **Frequenz** | Täglich um 00:00 UTC |
| **Entscheider** | **Beide** — gemeinsame Entscheidung erforderlich |
| **Aktion** | Edge-Analyse durchführen, ggf. Projektende |

**Rationale:** Unser gesamter Edge basiert auf Oracle Lag ≥ 0.35%. Wenn Chainlink die Update-Frequenz erhöht oder andere strukturelle Änderungen vornimmt, existiert unser Edge nicht mehr.

**Mögliche Ursachen:**
- Chainlink erhöht Update-Frequenz
- Deviation Threshold gesenkt
- Markt wird weniger volatil
- Konkurrenz-Bots arbitrieren den Edge weg

---

## 2. Eskalations-Matrix

| Trigger | Severity | Automatisch? | Entscheider | Nächster Schritt |
|---------|----------|--------------|-------------|------------------|
| Win Rate < 52% (50+ Trades) | HIGH | Nein | Person B | Pause + Analyse |
| Brier > 0.24 (14 Tage) | HIGH | Nein | Person B | Retraining oder Ende |
| Drawdown > 20% | CRITICAL | **JA** | System | Hard Stop |
| System offline > 24h | MEDIUM | Nein | Person A | Fix oder Pause |
| Oracle Lag < 0.35% (7 Tage) | CRITICAL | Nein | Beide | Analyse oder Ende |

---

## 3. Wiederaufnahme-Protokoll

Nach einem Kill-Switch Trigger darf Trading nur wieder aufgenommen werden wenn:

1. **Root-Cause identifiziert** — Dokumentiert in `docs/incident_reports/`
2. **Fix implementiert** — Code-Änderung oder Parameter-Anpassung
3. **Beide Personen zustimmen** — Schriftliche Bestätigung
4. **Paper Trading Phase** — Mindestens 20 erfolgreiche Paper Trades vor Live

---

## 4. Unterschriften

Durch Unterschrift bestätige ich, dass ich dieses Kill-Switch Protokoll gelesen und verstanden habe. Ich verpflichte mich, alle Bedingungen einzuhalten und bei Auslösung sofort zu handeln.

### Person A (Data Engineering)

**Name:** Matej

**Unterschrift:** _________________________________

**Datum:** _______________

---

### Person B (Strategy)

**Name:** Lukis

**Unterschrift:** _________________________________

**Datum:** _______________

---

## 5. Änderungshistorie

| Datum | Version | Änderung | Autor |
|-------|---------|----------|-------|
| 2026-02-23 | 1.0 | Initial Version | Person B |

---

*Dieses Dokument ist verbindlich. Live Trading darf erst beginnen, wenn beide Unterschriften vorliegen.*

*Projekt: Polymarket BTC 5-Min Oracle Lag Arbitrage*
