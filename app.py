from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
import httpx
from datetime import datetime, timedelta
from typing import Optional, Dict
import io
import csv
import re

app = FastAPI()

LOUISVILLE_API = "https://services1.arcgis.com/79kfd2K6fskCAkyg/arcgis/rest/services/Code_Enforcement___Property_Maintenance_Violations/FeatureServer/0/query"

async def fetch_louisville_violations(limit: int = 200):
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        
        params = {
            'where': f"INSPECTION_DATE >= timestamp '{start_str} 00:00:00' AND INSPECTION_DATE <= timestamp '{end_str} 23:59:59'",
            'outFields': '*',
            'f': 'json',
            'returnGeometry': 'false',
            'resultRecordCount': limit
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(LOUISVILLE_API, params=params)
            data = response.json()
            
            if 'features' in data:
                violations = []
                for feature in data['features']:
                    attrs = feature.get('attributes', {})
                    score = calculate_distress_score(attrs)
                    
                    violations.append({
                        'address': attrs.get('SITE_ADDRESS', 'Unknown Address'),
                        'violation_type': attrs.get('VIOLATION_CODE_DESCRIPTION', 'Unknown'),
                        'case_id': attrs.get('CASE_NUMBER', 'N/A'),
                        'status': attrs.get('CASE_STATUS', 'Open'),
                        'date': format_date(attrs.get('INSPECTION_DATE', '')),
                        'score': score,
                        'zip': extract_zip(attrs.get('SITE_ADDRESS', ''))
                    })
                
                violations.sort(key=lambda x: x['score'], reverse=True)
                return violations
        
        return []
    
    except Exception as e:
        print(f"Error: {e}")
        return []

def calculate_distress_score(attrs: Dict) -> int:
    score = 5
    violation = str(attrs.get('VIOLATION_CODE_DESCRIPTION', '')).lower()
    status = str(attrs.get('CASE_STATUS', '')).lower()
    
    if any(word in violation for word in ['structural', 'unsafe', 'condemned', 'collapse']):
        score = 9
    elif any(word in violation for word in ['fire', 'electrical', 'hazard', 'health']):
        score = 8
    elif any(word in violation for word in ['overgrown', 'trash', 'debris', 'vacant']):
        score = 6
    
    if 'open' in status or 'active' in status:
        score = min(score + 1, 10)
    
    return score

def format_date(timestamp):
    try:
        if timestamp:
            dt = datetime.fromtimestamp(int(timestamp) / 1000)
            return dt.strftime('%b %d, %Y')
    except:
        pass
    return 'Unknown'

def extract_zip(address: str) -> str:
    match = re.search(r'\b\d{5}\b', address)
    return match.group() if match else ''

@app.get("/", response_class=HTMLResponse)
async def home(search: Optional[str] = None, min_score: int = 0):
    all_violations = await fetch_louisville_violations(200)
    
    filtered = all_violations
    
    if search:
        search_lower = search.lower()
        filtered = [v for v in filtered if 
                   search_lower in v['address'].lower() or 
                   search_lower in v['violation_type'].lower()]
    
    if min_score > 0:
        filtered = [v for v in filtered if v['score'] >= min_score]
    
    total = len(all_violations)
    high_distress = sum(1 for v in all_violations if v['score'] >= 8)
    vacant = sum(1 for v in all_violations if 'vacant' in v['violation_type'].lower())
    
    zips = {}
    for v in all_violations:
        if v['zip']:
            zips[v['zip']] = zips.get(v['zip'], 0) + 1
    top_zips = sorted(zips.items(), key=lambda x: x[1], reverse=True)[:5]
    
    property_cards = ""
    for idx, v in enumerate(filtered[:50], 1):
        color = 'red' if v['score'] >= 8 else 'orange' if v['score'] >= 6 else 'yellow'
        
        property_cards += f"""
        <div class="border-l-4 border-{color}-500 p-4 bg-{color}-50 rounded-lg hover:shadow-md transition mb-3">
            <div class="flex justify-between items-start gap-4">
                <div class="flex-1">
                    <div class="flex items-center gap-2 mb-2">
                        <span class="bg-gray-200 text-gray-700 px-2 py-1 rounded text-xs font-bold">#{idx}</span>
                        <div class="font-bold text-gray-800">{v['address']}</div>
                    </div>
                    <div class="text-sm text-gray-600 mb-2">{v['violation_type']}</div>
                    <div class="flex flex-wrap gap-3 text-xs text-gray-500">
                        <span>📋 {v['case_id']}</span>
                        <span>📊 {v['status']}</span>
                        <span>📅 {v['date']}</span>
                    </div>
                </div>
                <div class="bg-{color}-500 text-white px-4 py-3 rounded-full font-bold text-xl">
                    {v['score']}
                </div>
            </div>
        </div>
        """
    
    hotspot_html = ""
    for zip_code, count in top_zips:
        hotspot_html += f"""
        <div class="bg-gradient-to-br from-red-50 to-orange-50 border-2 border-red-300 rounded-xl p-4">
            <div class="flex justify-between items-center">
                <div>
                    <div class="text-2xl font-bold text-red-700">{zip_code}</div>
                    <div class="text-sm text-gray-600">ZIP Code</div>
                </div>
                <div class="text-3xl font-bold text-red-600">{count}</div>
            </div>
        </div>
        """
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Hayseed Properties</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <meta name="viewport" content="width=device-width, initial-scale=1">
    </head>
    <body class="bg-gradient-to-br from-gray-50 to-blue-50">
        <div class="max-w-7xl mx-auto p-4 md:p-6">
            <div class="bg-gradient-to-r from-blue-600 via-purple-600 to-pink-600 text-white rounded-2xl p-6 mb-6 shadow-2xl">
                <div class="flex items-center justify-between mb-3">
                    <div>
                        <h1 class="text-3xl md:text-4xl font-bold mb-2">🏠 Hayseed Properties</h1>
                        <p class="text-sm md:text-base opacity-90">Louisville Property Distress Analysis System</p>
                    </div>
                    <a href="/export" class="bg-white/20 hover:bg-white/30 px-4 py-2 rounded-lg text-sm font-medium transition">
                        📥 Export CSV
                    </a>
                </div>
                <div class="flex flex-wrap gap-3 text-xs md:text-sm opacity-90">
                    <span>📡 Live Data</span>
                    <span>🔄 Auto-updates</span>
                    <span>📍 Louisville, KY</span>
                    <span>🔒 Secure</span>
                </div>
            </div>
            
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                <div class="bg-white p-6 rounded-xl shadow-lg border-l-4 border-blue-500">
                    <div class="text-4xl font-bold text-blue-600">{total}</div>
                    <div class="text-gray-600 mt-1">Total Violations</div>
                    <div class="text-xs text-gray-400 mt-1">Last 30 days</div>
                </div>
                
                <div class="bg-white p-6 rounded-xl shadow-lg border-l-4 border-red-500">
                    <div class="text-4xl font-bold text-red-600">{high_distress}</div>
                    <div class="text-gray-600 mt-1">High Distress</div>
                    <div class="text-xs text-gray-400 mt-1">Score ≥ 8</div>
                </div>
                
                <div class="bg-white p-6 rounded-xl shadow-lg border-l-4 border-orange-500">
                    <div class="text-4xl font-bold text-orange-600">{vacant}</div>
                    <div class="text-gray-600 mt-1">Potentially Vacant</div>
                    <div class="text-xs text-gray-400 mt-1">Flagged</div>
                </div>
            </div>

            <div class="bg-white rounded-xl shadow-lg p-6 mb-6">
                <h2 class="text-xl font-bold mb-4">🔍 Search & Filter</h2>
                <form method="get" class="space-y-4">
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <input type="text" name="search" value="{search or ''}" placeholder="Search address..." 
                            class="px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-blue-500 focus:outline-none w-full"/>
                        <select name="min_score" class="px-4 py-3 border-2 border-gray-300 rounded-lg">
                            <option value="0">All Scores</option>
                            <option value="8">Critical (8+)</option>
                            <option value="6">High (6+)</option>
                        </select>
                        <button type="submit" class="bg-blue-600 text-white font-bold py-3 px-6 rounded-lg">
                            Apply
                        </button>
                    </div>
                </form>
                <div class="mt-3 text-sm text-gray-600">
                    Showing {len(filtered)} of {total} properties
                </div>
            </div>

            {f'<div class="bg-white rounded-xl shadow-lg p-6 mb-6"><h2 class="text-xl font-bold mb-4">🗺️ Hotspots</h2><div class="grid grid-cols-1 md:grid-cols-5 gap-4">{hotspot_html}</div></div>' if hotspot_html else ''}

            <div class="bg-white rounded-xl shadow-lg p-6">
                <h2 class="text-xl font-bold mb-4">📋 Properties</h2>
                {property_cards if property_cards else '<p class="text-gray-500 text-center py-8">No properties found</p>'}
            </div>

            <div class="mt-6 text-center text-sm text-gray-500 bg-white rounded-xl p-4">
                <p>Last updated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
                <p class="mt-2"><a href="/mobile" class="text-blue-600">📱 Mobile Version</a></p>
            </div>
        </div>
    </body>
    </html>
    """

@app.get("/mobile", response_class=HTMLResponse)
async def mobile():
    violations = await fetch_louisville_violations(100)
    critical = [v for v in violations if v['score'] >= 8][:10]
    
    property_cards = ""
    for idx, v in enumerate(critical, 1):
        property_cards += f"""
        <div class="bg-red-50 border-l-4 border-red-500 p-4 rounded-lg mb-3">
            <div class="flex justify-between items-center">
                <div class="flex-1">
                    <div class="font-bold text-sm mb-1">{v['address'][:40]}...</div>
                    <div class="text-xs text-gray-600">{v['violation_type'][:50]}</div>
                </div>
                <div class="bg-red-500 text-white w-14 h-14 rounded-full flex items-center justify-center font-bold text-xl">
                    {v['score']}
                </div>
            </div>
        </div>
        """
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Hayseed Mobile</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-50">
        <div class="bg-gradient-to-r from-blue-600 to-purple-600 text-white p-4">
            <h1 class="text-2xl font-bold">🏠 Hayseed Mobile</h1>
            <p class="text-sm opacity-90">Field Inspector</p>
        </div>
        
        <div class="p-4 space-y-4">
            <div class="grid grid-cols-2 gap-3">
                <div class="bg-gradient-to-br from-red-500 to-red-600 rounded-xl p-4 text-white">
                    <div class="text-3xl font-bold">{len(critical)}</div>
                    <div class="text-sm">Critical</div>
                </div>
                <div class="bg-gradient-to-br from-blue-500 to-blue-600 rounded-xl p-4 text-white">
                    <div class="text-3xl font-bold">{len(violations)}</div>
                    <div class="text-sm">Total</div>
                </div>
            </div>

            <h2 class="font-bold">🚨 Critical Properties</h2>
            {property_cards if property_cards else '<p class="text-gray-500 text-center py-8">No critical properties</p>'}

            <div class="text-center text-xs text-gray-500 bg-white rounded-lg p-4">
                <p>Updated: {datetime.now().strftime('%I:%M %p')}</p>
            </div>
        </div>
    </body>
    </html>
    """

@app.get("/export")
async def export_csv():
    violations = await fetch_louisville_violations(200)
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['#', 'Address', 'Violation', 'Case', 'Status', 'Date', 'Score', 'ZIP'])
    
    for idx, v in enumerate(violations, 1):
        writer.writerow([idx, v['address'], v['violation_type'], v['case_id'], v['status'], v['date'], v['score'], v['zip']])
    
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=hayseed_{datetime.now().strftime('%Y%m%d')}.csv"}
    )

@app.get("/health")
async def health():
    return {"status": "healthy", "source": "Louisville Open Data"}
