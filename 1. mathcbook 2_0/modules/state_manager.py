import json
import os

class StateManager:
    def __init__(self, state_file="state.json"):
        self.state_file = state_file

    def load(self):
        if not os.path.exists(self.state_file): return {}
        with open(self.state_file, "r") as f: return json.load(f)

    def save(self, states):
        with open(self.state_file, "w") as f: json.dump(states, f, indent=2)