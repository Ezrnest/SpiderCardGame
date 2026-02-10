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
  - click `Start New Game`, `Daily Challenge`, or `Game Settings`.
- Settings page:
  - `Difficulty`: `Easy(1-suit) / Medium(2-suit) / Hard(4-suit)`
  - `Card Face`: `Classic / Minimal / Neo`
  - `Theme`: `Forest / Ocean / Sunset`
- In game:
  - Mouse drag-and-drop: press on a valid sequence, drag, release on destination stack.
  - Click the deck (top-right card pile) to deal.
  - `N`: start a normal new game
  - `D`: deal cards
  - `U`: undo
  - `R`: redo
  - `S`: open settings page
  - `M`: back to menu

## Future plan
The latest version of spider card game on Windows10 can generate games of different difficulty. 
I am thinking of algorithms to implement this feature.
