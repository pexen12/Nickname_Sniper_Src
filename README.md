# 🎯 Username Checker

Narzędzie do masowego sprawdzania dostępności nazw użytkownika na 13 platformach jednocześnie. Wpisz zakres długości, wybierz platformę — program robi resztę.

---

## ✨ Co potrafi

- 🔍 Sprawdza dostępność nazw na **13 platformach**
- ⚡ Wielowątkowość — do 20 wątków równolegle
- 📊 Pasek postępu w czasie rzeczywistym (%, ETA, szybkość)
- 💾 Automatycznie zapisuje dostępne nazwy do pliku `.txt`
- 🎛️ Pełna kontrola: długość nazwy, zestaw znaków, liczba wątków

---

## 🌐 Obsługiwane platformy

| Platforma | Wymaga klucza? |
|-----------|---------------|
| GitHub | ✅ Nie |
| npm | ✅ Nie |
| PyPI | ✅ Nie |
| crates.io | ✅ Nie |
| YouTube | ✅ Nie |
| X / Twitter | ✅ Nie |
| Discord | ✅ Nie |
| Minecraft | ✅ Nie |
| Roblox | ✅ Nie |
| Steam | ✅ Nie |
| Epic Games | ✅ Nie |
| Gmail | ✅ Nie (wyniki orientacyjne) |
| Twitch | ⚠️ Darmowy klucz z dev.twitch.tv |

---

## 🚀 Instalacja i uruchomienie

```bash
pip install requests
python username_checker.py
```

### Zbuduj plik .EXE (Windows)

```bash
pip install pyinstaller
python -m PyInstaller --onefile --console --name "UsernameChecker" username_checker.py
```

Gotowy plik znajdziesz w folderze `dist/`.

---

## 📋 Wymagania

- Python 3.8+
- Biblioteka `requests`

---

## ⚠️ Uwaga

Program używa wyłącznie oficjalnych i publicznych metod sprawdzania (API, publiczne profile). Przestrzegaj regulaminów poszczególnych serwisów. Zbyt duża liczba zapytań może skutkować tymczasową blokadą IP.

---

*Autor: **Pexen***
