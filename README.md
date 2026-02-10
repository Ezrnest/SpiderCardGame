# Spider Card Game
A spider card game written in Python.

## Run the game
Simply runs base/TkInterface.py with python.
Modern prototype UI (with animation queue) can be started with:
`python -m modern_ui.run`

## Introduction
The game is basically the same as the spider card game defautly installed on Windows. 
In addition, players can view their statistics and save and load games. 
This implementation supports both command line interface and visual interface. 
The file `Core.py` contains the basic logic of the game. The files `CommandLine.py` and `TkInterface.py` are 
implementation of two kinds of interfaces.

## Modern UI controls
- Mouse: click source sequence, then click destination stack.
- `N`: new game
- `D`: deal cards
- `U`: undo
- `R`: redo

## Future plan
The latest version of spider card game on Windows10 can generate games of different difficulty. 
I am thinking of algorithms to implement this feature.
