# Spider Card Game
A spider card game written in Python.

## Run the game
Simply runs base/TkInterface.py with python.
Modern prototype UI (menu + drag and drop + effects) can be started with:
`python -m modern_ui.run`

## Introduction
The game is basically the same as the spider card game defautly installed on Windows. 
In addition, players can view their statistics and save and load games. 
This implementation supports both command line interface and visual interface. 
The file `Core.py` contains the basic logic of the game. The files `CommandLine.py` and `TkInterface.py` are 
implementation of two kinds of interfaces.

## Modern UI controls
- Menu:
  - click `Start New Game`, `Continue Game`, `Daily Challenge`, `Statistics`, or `Game Settings`.
  - `Save Slot` supports 3 slots; `Continue Game` uses current slot.
- Settings page:
  - `Difficulty`: `Easy(1-suit) / Medium(2-suit) / Hard(4-suit)`
  - `Card Style`: `Classic / Minimal / Neo / ArtDeck / NeoGrid / VintageGold / SakuraInk` (front and back are unified per style)
  - `Theme`: `Forest / Ocean / Sunset`
  - `Font Scale`: `Small / Normal / Large / X-Large / Huge`
  - Settings are persisted to `modern_ui/settings.ini`.
  - Game progress is auto-saved per slot to `modern_ui/savegame_slot1.txt` ... `savegame_slot3.txt`.
  - Statistics are persisted to `modern_ui/stats.json`.
- In game:
  - Mouse drag-and-drop: press on a valid sequence, drag, release on destination stack.
  - Click the deck (top-right card pile) to deal.
  - `N`: start a normal new game
  - `C`: continue saved game (from menu)
  - `D`: deal cards
  - `U`: undo
  - `R`: redo
  - `S`: open settings page
  - `M`: back to menu
  - `H`: Hint+ (top candidate moves with risk notes)
  - `P`: open statistics page
  - In settings page: `F` cycles font scale.
  - Deck generators:
    - `python3 modern_ui/assets/scripts/generate_art_deck.py`
    - `python3 modern_ui/assets/scripts/generate_extra_decks.py`
  - Generators output both display-size assets and HD source assets.

## Future plan
The latest version of spider card game on Windows10 can generate games of different difficulty. 
I am thinking of algorithms to implement this feature.
