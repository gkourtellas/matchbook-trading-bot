"""Adds a "Win side" dropdown (Either / Home only / Away only) to the
dashboard. Run once from the project root:

    python3 patch_dashboard.py

All-or-nothing: if any spot isn't found, it changes nothing.
"""

import re

PATH = "src/dashboard.py"

with open(PATH, encoding="utf-8") as f:
    content = f.read()

FIELD_HTML = '''
        <div class="field">
          <label>Win side <span style="color:var(--muted); text-transform:none;">(Match Odds / Moneyline only)</span></label>
          <select id="f_runner_side">
            <option value="">— either —</option>
            <option value="home">Home only</option>
            <option value="away">Away only</option>
          </select>
        </div>'''

# (regex, replacement) — each must match exactly once.
edits = [
    # 1. dropdown in the single-sport form, right after the BTTS dropdown
    (r'(<option value="No">No</option>\s*</select>\s*</div>)',
     lambda m: m.group(1) + FIELD_HTML),
    # 2. fill it when opening a strategy
    (r"(document\.getElementById\('f_btts_direction'\)\.value = s\.btts_direction \?\? '';)",
     lambda m: m.group(1) + "\n  document.getElementById('f_runner_side').value = s.runner_side ?? '';"),
    # 3. read it + check it on save
    (r"(const bttsDirection = document\.getElementById\('f_btts_direction'\)\.value;)",
     lambda m: m.group(1) + """
  const runnerSide = document.getElementById('f_runner_side').value;
  if (runnerSide && ((market !== 'Match Odds' && market !== 'Moneyline') || betMode !== 'normal' || betSide !== 'back')) {
    showError('Win side (Home/Away) only works for Match Odds / Moneyline, normal mode, back side.');
    return;
  }"""),
    # 4. store it
    (r"(btts_direction: market === 'Both Teams To Score' \? bttsDirection : null,)",
     lambda m: m.group(1) + "\n    runner_side: runnerSide || null,"),
    # 5. show it in the strategy list
    (r"(\$\{s\.btts_direction \? ' BTTS: ' \+ s\.btts_direction : ''\})",
     lambda m: m.group(1) + "${s.runner_side ? ' · ' + s.runner_side.toUpperCase() + ' only' : ''}"),
    # 6. server-side check
    (r"(return f\"Strategy '\{s\['name'\]\}': btts_direction is set but market isn't 'Both Teams To Score'\.\")",
     lambda m: m.group(1) + '''

        runner_side = s.get("runner_side")
        if runner_side not in (None, "", "home", "away"):
            return f"Strategy '{s['name']}': runner_side must be 'home' or 'away'."
        if runner_side and (market not in ("Match Odds", "Moneyline") or bet_mode != "normal" or bet_side != "back"):
            return (f"Strategy '{s['name']}': runner_side only works for Match Odds/Moneyline, "
                    f"normal mode, back side.")'''),
    # 7. build number, so you can see the new version is live
    (r'BUILD_VERSION = "v13"',
     lambda m: 'BUILD_VERSION = "v14"'),
]

for i, (pattern, _) in enumerate(edits, 1):
    count = len(re.findall(pattern, content))
    if count != 1:
        print(f"Edit #{i}: found {count} match(es), need exactly 1. Nothing changed.")
        raise SystemExit(1)

for pattern, repl in edits:
    content = re.sub(pattern, repl, content, count=1)

with open(PATH, "w", encoding="utf-8") as f:
    f.write(content)

print("Done. dashboard.py now v14. Restart the dashboard container.")
