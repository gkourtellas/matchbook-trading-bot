# Matchbook Bot v2.0 - High-Level Plan

## Objective
To evolve the existing single-strategy bot into a scalable, multi-strategy engine capable of running multiple betting strategies in parallel.

## Phase 1: Configuration Management
* **Consolidation**: Move all strategy-specific parameters from hardcoded values into a centralized `settings.json` file.
* **Format**: Update settings to use a list format, allowing the addition of new strategies without changing code.

## Phase 2: Engine Refactoring
* **Orchestrator Development**: Create a "Launcher" script that initializes the system.
* **Parallel Execution**: Modify the engine to monitor the settings file and start multiple strategies simultaneously without them blocking each other.

## Phase 3: Shared Infrastructure
* **Common Session**: Implement a shared authentication service so all strategies use the same connection to Matchbook.
* **Standardization**: Create a standard "template" that all new strategies must follow, ensuring they communicate with the bot engine in the same way.

## Phase 4: Monitoring & Deployment
* **Unified Reporting**: Standardize logging and Telegram alerts to identify which strategy is reporting information.
* **Testing**: Validate parallel execution to ensure rate limits are handled gracefully across all active strategies.
