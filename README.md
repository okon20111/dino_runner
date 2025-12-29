# 🦖 Dino Runner

Dino Runner to dynamiczna gra 2D typu **endless runner**, napisana w Pythonie z użyciem biblioteki **Pygame**.  
Gracz steruje dinozaurem, którego zadaniem jest omijanie przeszkód, przeskakiwanie ich i przetrwanie jak najdłużej, podczas gdy poziom trudności stopniowo rośnie.

---

## 🎮 Funkcje gry

- płynna animacja i przewijane tło
- system poziomów oparty na zmianie tła
- rosnąca prędkość i trudność gry
- realistyczna fizyka skoku (grawitacja + prędkość)
- precyzyjne kolizje oparte na maskach
- rozbudowane menu (start, pauza, game over, ustawienia)
- ekran odliczania przed startem gry
- pasek ładowania poziomu
- własny kursor
- zapisywanie ustawień użytkownika (dźwięk, sterowanie)

---

## 🕹️ Sterowanie

Domyślnie:
- **Spacja** – skok

Dostępne alternatywy (do wyboru w ustawieniach):
- **Strzałka w górę**
- **W**

---

## ⚙️ Ustawienia

Ustawienia są zapisywane lokalnie w pliku:
- `setting.json`

Dostępne opcje:
- włączanie / wyłączanie dźwięku skoku
- zmiana klawisza skoku

---

## 🧠 Logika gry

- Dinozaur porusza się po stałej osi X
- Przeszkody generowane są dynamicznie przez `ObstacleManager`
- Trudność zwiększa się wraz z czasem gry oraz zmianą tła
- Kolizje wykrywane są za pomocą masek (`pygame.mask`)
- Po zderzeniu gra przechodzi do ekranu **Game Over**

---

## 📁 Struktura projektu

