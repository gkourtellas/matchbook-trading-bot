with open("src/dashboard.py") as f:
    content = f.read()

duplicate_block = '''@app.route("/manifest.json")
def manifest():
    return jsonify({
        "name": "Matchbook Dashboard",
        "short_name": "Matchbook",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#0a0e14",
        "theme_color": "#0a0e14",
        "orientation": "portrait-primary",
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    })


'''

count = content.count(duplicate_block)
if count == 0:
    print("Block not found — nothing changed. Paste more context, don't guess.")
else:
    content = content.replace(duplicate_block, "", 1)
    with open("src/dashboard.py", "w") as f:
        f.write(content)
    print(f"Removed the duplicate block ({count} found, removed 1).")
