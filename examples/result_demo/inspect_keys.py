import json, glob, os
for p in sorted(glob.glob(os.path.join('D:/DevelopAndGrowth/Agents/RachelAgent/results/result_demo', '*.json'))):
    print('=== ' + os.path.basename(p) + ' ===')
    with open(p, encoding='utf-8') as f:
        d = json.load(f)
    print('TOP:', list(d.keys()))
    c = d.get('current') or {}
    if isinstance(c, dict):
        print('CURRENT:', list(c.keys()))
    s = d.get('status') or {}
    if isinstance(s, dict):
        print('STATUS:', list(s.keys()))
    print()
