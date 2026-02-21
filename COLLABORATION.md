# Collaboration Guide

## Repository

**URL:** https://github.com/LutzKol/polymarket-bot

## Ordnerstruktur

```
polymarket-bot/
├── person-a/     # Matej's Arbeitsbereich
├── person-b/     # Lutz's Arbeitsbereich
├── shared/       # Gemeinsamer Code (Utilities, Config)
└── docs/         # Projekt-Dokumentation (falls root-level)
```

### Regeln
- **person-a/**: Nur Matej bearbeitet hier
- **person-b/**: Nur Lutz bearbeitet hier
- **shared/**: Gemeinsam genutzt — vor Änderungen absprechen

## Für Matej: Repo clonen

```bash
# 1. Repository clonen
git clone https://github.com/LutzKol/polymarket-bot.git

# 2. In den Ordner wechseln
cd polymarket-bot

# 3. Deinen Arbeitsbereich einrichten
cd person-a
```

## Änderungen pushen

```bash
# 1. Aktuelle Änderungen vom Server holen
git pull

# 2. Dateien zum Commit hinzufügen
git add .

# 3. Commit erstellen (aussagekräftige Nachricht!)
git commit -m "Beschreibung der Änderung"

# 4. Zum Server pushen
git push
```

## Workflow-Tipps

1. **Immer zuerst `git pull`** — verhindert Merge-Konflikte
2. **Kleine, häufige Commits** — leichter nachzuvollziehen
3. **Eigenen Ordner nutzen** — vermeidet Konflikte
4. **shared/ nur nach Absprache ändern**

## Kontakt

Bei Fragen oder Konflikten: Kurz absprechen bevor ihr pushed!
