# Matchbook Bot v2.0 - Detailed Technical Plan

## 1. Updating Settings
We will move from a hardcoded setup in `strategy_one.py` to a dynamic configuration.
* **File Structure**: `config/settings.json` will contain an array of objects. Each object will define the `strategy_name`, `odds_range`, `stake_amount`, and `sport_id`.
* **Benefit**: Adding a new strategy becomes as simple as adding a new block of text to this JSON file.

## 2. The Orchestrator (The "Launcher")
We will replace the current manual start with a script that:
* Reads `settings.json`.
* Loops through the list of strategies.
* Spawns independent "workers" for each strategy.
* Ensures that even if one strategy encounters an error, the others continue running.

## 3. Engine Refactoring
* **The "Worker" Pattern**: Each strategy will be converted into a self-contained module.
* **Shared Session**: We will implement a "Client Factory." Instead of each strategy logging in, they will request a valid session token from a central service. If the token is expired, the service refreshes it once, and all strategies resume using the new token.

## 4. Communication & Logging
* **Identity**: Every message sent to Telegram will now start with the `[Strategy Name]` tag so you can instantly see which strategy placed a bet or reported a settlement.
* **Central Logs**: All logs will be funneled into a single, clean log file, with each line tagged by the strategy name.

## 5. Implementation Roadmap
1. **Prepare Config**: Define the new `settings.json` format.
2. **Standardize Strategy**: Wrap your current strategy code into a "Run" function that accepts settings as an input.
3. **Build Launcher**: Create the script that runs multiple "Run" functions at once.
4. **Deploy**: Update the Docker configuration to point to the new Launcher instead of the individual strategy file.
