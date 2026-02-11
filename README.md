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
  - `Suit Count`: `1 / 2 / 3 / 4`
  - `Difficulty Bucket`: `Easy / Medium / Hard`
  - `Card Style`: `Classic / FourColorClassic / Minimal / Neo / ArtDeck / NeoGrid / VintageGold / SakuraInk` (front and back are unified per style)
  - `Theme`: `Forest / Ocean / Sunset`
  - `Font Scale`: `Small / Normal / Large / X-Large / Huge`
  - Settings are persisted to `modern_ui/settings.ini`.
  - Game progress is auto-saved per slot to `modern_ui/savegame_slot1.txt` ... `savegame_slot3.txt`.
  - Statistics are persisted to `modern_ui/stats.json`.
- In game:
  - Mouse drag-and-drop: press on a valid sequence, drag, release on destination stack.
  - Click the deck (top-right card pile) to deal.
  - `N`: start a normal new game
  - `I`: input a seed and start a seeded game
  - `G`: restart current game with the same seed (when seed is available)
  - `C`: continue saved game (from menu)
  - `D`: deal cards
  - `U`: undo
  - `R`: redo
  - `V`: heuristic demo one step (no solver search)
  - `A`: solver auto-play (search then auto execute plan)
  - `X`: stop solver demo / auto-play
  - `S`: open settings page
  - `M`: back to menu
  - `H`: Hint+ (top candidate moves with risk notes)
  - `P`: open statistics page
  - In settings page:
    - `1/2/3/4`: set suit count
    - `Q/W/E`: set difficulty bucket to Easy/Medium/Hard
    - `B`: cycle difficulty bucket
    - `F`: cycle font scale
  - Deck generators:
    - `python3 modern_ui/assets/scripts/generate_art_deck.py`
    - `python3 modern_ui/assets/scripts/generate_extra_decks.py`
  - Generators output both display-size assets and HD source assets.

## Solver and seed pipeline
This project now includes a first version of `solver/analyzer` and a batch seed pipeline to pre-compute solvability and difficulty, then feed seeds back into UI by suit-count + difficulty bucket.

- Solver module:
  - `solver/analyzer.py`
  - search uses state dedup/canonicalization and staged widening.
  - difficulty score is a raw (unbounded) numeric score from search/solution features.
  - `unknown` means search budget/time limit reached (not proven unsolvable).

- Seed mining / pool build:
  - `solver/seed_miner.py`: quick batch scan for solver outcomes.
  - `solver/seed_pool_builder.py`: builds bucketed seed pool artifacts.

- Pool outputs (default under `data/`):
  - `data/seed_pool_{suits}s.json` (meta + quantiles + buckets + stats)
  - `data/seed_pool_{suits}s_rows.csv` (one compact merged table per seed)
    - columns: `seed,status,score,bucket,reason,elapsed_ms,expanded_nodes,unique_states`
  - `buckets` contains `Easy/Medium/Hard/unknown`.
  - builder always merges by `seed` when not using `--overwrite`.

- UI seed consumption:
  - Modern UI reads seed pool by selected suit count and difficulty bucket.
  - primary path: `data/seed_pool_{suits}s.json`
  - legacy fallback path: `modern_ui/seed_pool_{suits}s.json`

## Commands
- Analyze one/multiple seeds:
  - `python -m solver.analyzer --seed 12345 --suits 4 --max-seconds 2`
- Build seed pool:
  - `python -m solver.seed_pool_builder --suits 4 --count 500 --max-seconds 10`
  - `--start-seed` is optional. If omitted, a random start seed is selected.
- Cluster run helper:
  - script path: `script/run.sh`
  - script mode:
    - `bash script/run.sh solver/seed_pool_builder.py amd_512 --suits 4 --count 500`
  - module mode:
    - `bash script/run.sh -m solver.seed_pool_builder amd_512 --suits 4 --count 500`
