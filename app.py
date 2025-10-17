from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
import httpx
from datetime import datetime, timedelta
from typing import Optional, Dict
import io, csv, re

app = FastAPI()

LOUISVILLE_API = "https://services1.arcgis.com/79kfd2K6fskCAkyg/arcgis/rest/services/Code_Enforcement___Property_Maintenance_Violations/FeatureServer/0/query"

async def fetch_violations(limit: int = 500):
    try:
        params = {'where': '1=1', 'outFields': '*', 'f': 'json', 'returnGeometry': 'false', 'resultRecordCount': limit}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(LOUISVILLE_API, params=params)
            data = response.json()
            if 'features' in data and data['features']:
                violations = []
                for feature in data['features']:
                    attrs = feature.get('attributes', {})
                    violations.append({
                        'address': str(attrs.get('SITE_ADDRESS', 'N/A')),
                        'violation_type': str(attrs.get('VIOLATION_CODE_DESCRIPTION', 'N/A')),
                        'case_id': str(attrs.get('CASE_NUMBER', 'N/A')),
                        'status': str(attrs.get('CASE_STATUS', 'Unknown')),
                        'date': format_date(attrs.get('INSPECTION_DATE')),
                        'score': calc_score(attrs),
                        'zip': extract_zip(str(attrs.get('SITE_ADDRESS', '')))
                    })
                violations.sort(key=lambda x: x['score'], reverse=True)
                return violations
    except: pass
    return demo_data()

def demo_data():
    return [
        {'address': '1234 Main St, Louisville, KY 40211', 'violation_type': 'Structural Damage', 'case_id': 'VM-001', 'status': 'Open', 'date': 'Oct 15, 2025', 'score': 9, 'zip': '40211'},
        {'address': '5678 Oak Ave, Louisville, KY 40212', 'violation_type': 'Fire Hazard', 'case_id': 'VM-002', 'status': 'Pending', 'date': 'Oct 14, 2025', 'score': 8, 'zip': '40212'},
        {'address': '910 Elm St, Louisville, KY 40203', 'violation_type': 'Overgrown - Vacant', 'case_id': 'VM-003', 'status': 'Open', 'date': 'Oct 13, 2025', 'score': 7, 'zip': '40203'},
        {'address': '2345 Broadway, Louisville, KY 40211', 'violation_type': 'Trash Accumulation', 'case_id': 'VM-004', 'status': 'Open', 'date': 'Oct 12, 2025', 'score': 6, 'zip': '40211'},
        {'address': '7890 Maple Dr, Louisville, KY 40214', 'violation_type': 'Condemned', 'case_id': 'VM-005', 'status': 'Active', 'date': 'Oct 10, 2025', 'score': 10, 'zip': '40214'},
    ]

def calc_score(attrs: Dict) -> int:
    score = 5
    v = str(attrs.get('VIOLATION_CODE_DESCRIPTION', '')).lower()
    if any(w in v for w in ['structural', 'unsafe', 'condemned']): score = 9
    elif any(w in v for w in ['fire', 'electrical', 'hazard']): score = 8
    elif any(w in v for w in ['overgrown', 'trash', 'vacant']): score = 6
    return score

def format_date(ts):
    try:
        if ts: return datetime.fromtimestamp(int(ts)/1000).strftime('%b %d, %Y')
    except: pass
    return 'Unknown'

def extract_zip(addr: str) -> str:
    m = re.search(r'\b\d{5}\b', addr)
    return m.group() if m else ''

@app.get("/", response_class=HTMLResponse)
async def home(search: Optional[str] = None, min_score: int = 0):
    violations = await fetch_violations(500)
    filtered = violations
    if search:
        filtered = [v for v in filtered if search.lower() in v['address'].lower() or search.lower() in v['violation_type'].lower()]
    if min_score > 0:
        filtered = [v for v in filtered if v['score'] >= min_score]
    
    total = len(violations)
    high = sum(1 for v in violations if v['score'] >= 8)
    vacant = sum(1 for v in violations if 'vacant' in v['violation_type'].lower())
    
    cards = ""
    for i, v in enumerate(filtered[:50], 1):
        c = 'red' if v['score'] >= 8 else 'orange' if v['score'] >= 6 else 'yellow'
        cards += f'<div class="border-l-4 border-{c}-500 p-4 bg-{c}-50 rounded mb-3"><div class="flex justify-between"><div><div class="font-bold">#{i} {v["address"]}</div><div class="text-sm text-gray-600">{v["violation_type"]}</div><div class="text-xs text-gray-500">📋 {v["case_id"]} • {v["status"]} • {v["date"]}</div></div><div class="bg-{c}-500 text-white px-4 py-3 rounded-full font-bold text-xl">{v["score"]}</div></div></div>'
    
    return f'''<!DOCTYPE html><html><head><title>Hayseed</title><script src="https://cdn.tailwindcss.com"></script><meta name="viewport" content="width=device-width,initial-scale=1"></head><body class="bg-gray-50"><div class="max-w-7xl mx-auto p-4"><div class="bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-xl p-6 mb-6"><div class="flex justify-between items-center mb-3"><div><h1 class="text-3xl font-bold">🏠 Hayseed Properties</h1><p class="text-sm opacity-90">Louisville Property Analysis</p></div><a href="/export" class="bg-white/20 px-4 py-2 rounded-lg text-sm">📥 Export CSV</a></div></div><div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6"><div class="bg-white p-6 rounded-xl shadow-lg border-l-4 border-blue-500"><div class="text-4xl font-bold text-blue-600">{total}</div><div class="text-gray-600">Total Violations</div></div><div class="bg-white p-6 rounded-xl shadow-lg border-l-4 border-red-500"><div class="text-4xl font-bold text-red-600">{high}</div><div class="text-gray-600">High Distress</div></div><div class="bg-white p-6 rounded-xl shadow-lg border-l-4 border-orange-500"><div class="text-4xl font-bold text-orange-600">{vacant}</div><div class="text-gray-600">Potentially Vacant</div></div></div><div class="bg-white rounded-xl shadow-lg p-6 mb-6"><h2 class="text-xl font-bold mb-4">🔍 Search</h2><form method="get" class="flex gap-4"><input type="text" name="search" value="{search or ''}" placeholder="Search..." class="flex-1 px-4 py-2 border rounded-lg"/><button class="bg-blue-600 text-white px-6 py-2 rounded-lg">Search</button></form><p class="mt-3 text-sm text-gray-600">Showing {len(filtered)} of {total}</p></div><div class="bg-white rounded-xl shadow-lg p-6"><h2 class="text-xl font-bold mb-4">📋 Properties</h2>{cards if cards else "<p class='text-gray-500 text-center py-8'>No properties found</p>"}</div><div class="mt-6 text-center text-sm text-gray-500 bg-white rounded-xl p-4"><p>Updated: {datetime.now().strftime("%b %d, %Y at %I:%M %p")}</p><p class="mt-2"><a href="/mobile" class="text-blue-600">📱 Mobile</a></p></div></div></body></html>'''

@app.get("/mobile", response_class=HTMLResponse)
async def mobile():
    violations = await fetch_violations(200)
    critical = [v for v in violations if v['score'] >= 8][:10]
    cards = ""
    for i, v in enumerate(critical, 1):
        cards += f'<div class="bg-red-50 border-l-4 border-red-500 p-4 rounded mb-3"><div class="flex justify-between"><div class="flex-1"><div class="font-bold text-sm">#{i} {v["address"][:40]}</div><div class="text-xs text-gray-600">{v["violation_type"][:50]}</div></div><div class="bg-red-500 text-white w-14 h-14 rounded-full flex items-center justify-center font-bold text-xl">{v["score"]}</div></div></div>'
    return f'''<!DOCTYPE html><html><head><title>Hayseed Mobile</title><script src="https://cdn.tailwindcss.com"></script><meta name="viewport" content="width=device-width,initial-scale=1"></head><body class="bg-gray-50"><div class="bg-gradient-to-r from-blue-600 to-purple-600 text-white p-4"><h1 class="text-2xl font-bold">🏠 Hayseed Mobile</h1><p class="text-sm">Field Inspector</p></div><div class="p-4 space-y-4"><div class="grid grid-cols-2 gap-3"><div class="bg-red-500 rounded-xl p-4 text-white"><div class="text-3xl font-bold">{len(critical)}</div><div class="text-sm">Critical</div></div><div class="bg-blue-500 rounded-xl p-4 text-white"><div class="text-3xl font-bold">{len(violations)}</div><div class="text-sm">Total</div></div></div><h2 class="font-bold">🚨 Critical Properties</h2>{cards if cards else "<p class='text-gray-500 text-center py-8'>None</p>"}<a href="/export" class="block bg-green-600 text-white text-center rounded-xl p-4 font-bold">📥 Export CSV</a></div></body></html>'''

@app.get("/export")
async def export():
    violations = await fetch_violations(500)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['#', 'Address', 'Violation', 'Case', 'Status', 'Date', 'Score', 'ZIP'])
    for i, v in enumerate(violations, 1):
        writer.writerow([i, v['address'], v['violation_type'], v['case_id'], v['status'], v['date'], v['score'], v['zip']])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=hayseed_{datetime.now().strftime('%Y%m%d')}.csv"})

@app.get("/health")
async def health():
    return {"status": "healthy"}
