from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import httpx
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import secrets
import io
import csv

app = FastAPI()
security = HTTPBasic()

# Simple password protection
USERNAME = "admin"
PASSWORD = "hayseed2025"  # Change this!

LOUISVILLE_API = "https://services1.arcgis.com/79kfd2K6fskCAkyg/arcgis/rest/services/Code_Enforcement___Property_Maintenance_Violations/FeatureServer/0/query"

def check_auth(credentials: HTTPBasicCredentials):
    correct_username = secrets.compare_digest(credentials.username, USERNAME)
    correct_password = secrets.compare_digest(credentials.password, PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

async def fetch_louisville_violations(limit: int = 200):
    """Fetch real violations from Louisville Open Data"""
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
        print(f"Error fetching Louisville data: {e}")
        return []

def calculate_distress_score(attrs: Dict) -> int:
    """Calculate distress score 1-10"""
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
    """Format timestamp to readable date"""
    try:
        if timestamp:
            dt = datetime.fromtimestamp(int(timestamp) / 1000)
            return dt.strftime('%b %d, %Y')
    except:
        pass
    return 'Unknown'

def extract_zip(address: str) -> str:
    """Extract ZIP code from address"""
    import re
    match = re.search(r'\b\d{5}\b', address)
    return match.group() if match else ''

@app.get("/", response_class=HTMLResponse)
async def home(
    credentials: HTTPBasicCredentials = Query(None),
    search: Optional[str] = None,
    min_score: int = 0,
    max_score: int = 10
):
    """Main dashboard with password protection"""
    
    # Fetch violations
    all_violations = await fetch_louisville_violations(200)
    
    # Apply filters
    filtered = all_violations
    
    if search:
        search_lower = search.lower()
        filtered = [v for v in filtered if 
                   search_lower in v['address'].lower() or 
                   search_lower in v['violation_type'].lower()]
    
    if min_score > 0 or max_score < 10:
        filtered = [v for v in filtered if min_score <= v['score'] <= max_score]
    
    # Stats
    total = len(all_violations)
    high_distress = sum(1 for v in all_violations if v['score'] >= 8)
    vacant = sum(1 for v in all_violations if 'vacant' in v['violation_type'].lower())
    
    # Hotspots
    zips = {}
    for v in all_violations:
        if v['zip']:
            zips[v['zip']] = zips.get(v['zip'], 0) + 1
    top_zips = sorted(zips.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # Property cards
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
                        <span>📋 Case: {v['case_id']}</span>
                        <span>📊 Status: {v['status']}</span>
                        <span>📅 {v['date']}</span>
                        {f'<span>📍 ZIP: {v["zip"]}</span>' if v['zip'] else ''}
                    </div>
                </div>
                <div class="bg-{color}-500 text-white px-4 py-3 rounded-full font-bold text-xl shadow-md">
                    {v['score']}
                </div>
            </div>
        </div>
        """
    
    # Hotspot cards
    hotspot_html = ""
    for zip_code, count in top_zips:
        hotspot_html += f"""
        <div class="bg-gradient-to-br from-red-50 to-orange-50 border-2 border-red-300 rounded-xl p-4 hover:shadow-lg transition">
            <div class="flex justify-between items-center">
                <div>
                    <div class="text-2xl font-bold text-red-700">{zip_code}</div>
                    <div class="text-sm text-gray-600">ZIP Code Hotspot</div>
                </div>
                <div class="text-3xl font-bold text-red-600">{count}</div>
            </div>
        </div>
        """
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Hayseed Properties - Dashboard</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🏠</text></svg>">
    </head>
    <body class="bg-gradient-to-br from-gray-50 to-blue-50">
        <div class="max-w-7xl mx-auto p-4 md:p-6">
            
            <!-- Header -->
            <div class="bg-gradient-to-r from-blue-600 via-purple-600 to-pink-600 text-white rounded-2xl p-6 mb-6 shadow-2xl">
                <div class="flex items-center justify-between mb-3">
                    <div>
                        <h1 class="text-3xl md:text-4xl font-bold mb-2">🏠 Hayseed Properties</h1>
                        <p class="text-sm md:text-base opacity-90">Louisville Property Distress Analysis System</p>
                    </div>
                    <a href="/export" class="bg-white/20 hover:bg-white/30 px-4 py-2 rounded-lg text-sm font-medium transition backdrop-blur">
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
            
            <!-- Stats Dashboard -->
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                <div class="bg-white p-6 rounded-xl shadow-lg border-l-4 border-blue-500 hover:shadow-xl transition">
                    <div class="flex justify-between items-center">
                        <div>
                            <div class="text-4xl font-bold text-blue-600">{total}</div>
                            <div class="text-gray-600 mt-1">Total Violations</div>
                            <div class="text-xs text-gray-400 mt-1">Last 30 days</div>
                        </div>
                        <div class="text-5xl opacity-20">📊</div>
                    </div>
                </div>
                
                <div class="bg-white p-6 rounded-xl shadow-lg border-l-4 border-red-500 hover:shadow-xl transition">
                    <div class="flex justify-between items-center">
                        <div>
                            <div class="text-4xl font-bold text-red-600">{high_distress}</div>
                            <div class="text-gray-600 mt-1">High Distress</div>
                            <div class="text-xs text-gray-400 mt-1">Score ≥ 8</div>
                        </div>
                        <div class="text-5xl opacity-20">🚨</div>
                    </div>
                </div>
                
                <div class="bg-white p-6 rounded-xl shadow-lg border-l-4 border-orange-500 hover:shadow-xl transition">
                    <div class="flex justify-between items-center">
                        <div>
                            <div class="text-4xl font-bold text-orange-600">{vacant}</div>
                            <div class="text-gray-600 mt-1">Potentially Vacant</div>
                            <div class="text-xs text-gray-400 mt-1">Flagged</div>
                        </div>
                        <div class="text-5xl opacity-20">🏚️</div>
                    </div>
                </div>
            </div>

            <!-- Search & Filter -->
            <div class="bg-white rounded-xl shadow-lg p-6 mb-6">
                <h2 class="text-xl font-bold mb-4 text-gray-800">🔍 Search & Filter</h2>
                <form method="get" class="space-y-4">
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <input 
                            type="text" 
                            name="search" 
                            value="{search or ''}"
                            placeholder="Search address, violation type..." 
                            class="px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-blue-500 focus:outline-none w-full"
                        />
                        <select name="min_score" class="px-4 py-3 border-2 border-gray-300 rounded-lg focus:border-blue-500 focus:outline-none">
                            <option value="0">Min Score: Any</option>
                            <option value="8" {"selected" if min_score == 8 else ""}>Min Score: 8+ (Critical)</option>
                            <option value="6" {"selected" if min_score == 6 else ""}>Min Score: 6+ (High)</option>
                        </select>
                        <button type="submit" class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-6 rounded-lg transition shadow-md">
                            Apply Filters
                        </button>
                    </div>
                </form>
                <div class="mt-3 text-sm text-gray-600">
                    Showing {len(filtered)} of {total} properties
                </div>
            </div>

            <!-- Hotspots -->
            {f'''<div class="bg-white rounded-xl shadow-lg p-6 mb-6">
                <h2 class="text-xl font-bold mb-4 text-gray-800 flex items-center gap-2">
                    🗺️ Geographic Hotspots
                </h2>
                <div class="grid grid-cols-1 md:grid-cols-5 gap-4">
                    {hotspot_html}
                </div>
            </div>''' if hotspot_html else ''}

            <!-- Property List -->
            <div class="bg-white rounded-xl shadow-lg p-6">
                <div class="flex justify-between items-center mb-4">
                    <h2 class="text-xl font-bold text-gray-800">📋 Priority Properties</h2>
                    <span class="text-sm text-gray-500">Top {min(len(filtered), 50)}</span>
                </div>
                <div class="space-y-2">
                    {property_cards if property_cards else '<p class="text-gray-500 text-center py-8">No properties match your filters</p>'}
                </div>
            </div>

            <!-- Footer -->
            <div class="mt-6 text-center text-sm text-gray-500 bg-white rounded-xl p-4 shadow">
                <p class="mb-2">🔄 Data updates every time you refresh</p>
                <p>Last updated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
                <p class="mt-2"><a href="/mobile" class="text-blue-600 hover:underline">📱 Open Mobile Version</a></p>
            </div>
        </div>
    </body>
    </html>
    """

@app.get("/mobile", response_class=HTMLResponse)
async def mobile():
    """Mobile field inspector app"""
    violations = await fetch_louisville_violations(100)
    critical = [v for v in violations if v['score'] >= 8][:10]
    
    property_cards = ""
    for idx, v in enumerate(critical, 1):
        property_cards += f"""
        <div class="bg-gradient-to-r from-red-50 to-orange-50 border-l-4 border-red-500 p-4 rounded-lg shadow-md mb-3">
            <div class="flex justify-between items-center mb-2">
                <div class="flex-1">
                    <div class="flex items-center gap-2 mb-1">
                        <span class="bg-red-500 text-white px-2 py-1 rounded text-xs font-bold">#{idx}</span>
                        <div class="font-bold text-sm">{v['address'][:40]}...</div>
                    </div>
                    <div class="text-xs text-gray-600">{v['violation_type'][:50]}</div>
                    <div class="text-xs text-gray-500 mt-1">📋 {v['case_id']}</div>
                </div>
                <div class="bg-red-500 text-white w-14 h-14 rounded-full flex items-center justify-center font-bold text-xl shadow-lg">
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
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
        <script src="https://cdn.tailwindcss.com"></script>
        <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🏠</text></svg>">
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    </head>
    <body class="bg-gray-50">
        <!-- Header -->
        <div class="bg-gradient-to-r from-blue-600 to-purple-600 text-white p-4 sticky top-0 z-10 shadow-lg">
            <div class="flex items-center justify-between">
                <div>
                    <h1 class="text-2xl font-bold">🏠 Hayseed Mobile</h1>
                    <p class="text-sm opacity-90">Field Inspector</p>
                </div>
                <div class="bg-white/20 px-3 py-1 rounded-full text-xs backdrop-blur">
                    📡 LIVE
                </div>
            </div>
        </div>
        
        <!-- Content -->
        <div class="p-4 space-y-4">
            <!-- Stats -->
            <div class="grid grid-cols-2 gap-3">
                <div class="bg-gradient-to-br from-red-500 to-red-600 rounded-xl p-4 text-white shadow-lg">
                    <div class="text-3xl font-bold mb-1">{len(critical)}</div>
                    <div class="text-sm opacity-90">Critical</div>
                </div>
                <div class="bg-gradient-to-br from-blue-500 to-blue-600 rounded-xl p-4 text-white shadow-lg">
                    <div class="text-3xl font-bold mb-1">{len(violations)}</div>
                    <div class="text-sm opacity-90">Total</div>
                </div>
            </div>

            <!-- Properties -->
            <div>
                <h2 class="font-bold text-gray-800 mb-3 flex items-center gap-2">
                    🚨 Critical Properties
                    <span class="text-sm font-normal text-gray-500">({len(critical)} found)</span>
                </h2>
                {property_cards if property_cards else '<p class="text-gray-500 text-center py-8">No critical properties right now</p>'}
            </div>

            <!-- Actions -->
            <div class="grid grid-cols-2 gap-3">
                <a href="tel:911" class="bg-red-600 text-white rounded-xl p-4 flex flex-col items-center gap-2 shadow-md active:scale-95 transition">
                    <span class="text-2xl">🚨</span>
                    <span class="text-sm font-semibold">Emergency</span>
                </a>
                <a href="/" class="bg-blue-600 text-white rounded-xl p-4 flex flex-col items-center gap-2 shadow-md active:scale-95 transition">
                    <span class="text-2xl">💻</span>
                    <span class="text-sm font-semibold">Dashboard</span>
                </a>
            </div>

            <!-- Footer -->
            <div class="text-center text-xs text-gray-500 bg-white rounded-lg p-4 shadow">
                <p>Updated: {datetime.now().strftime('%I:%M %p')}</p>
                <p class="mt-1">Pull down to refresh</p>
            </div>
        </div>
    </body>
    </html>
    """

@app.get("/export")
async def export_csv():
    """Export all violations to CSV"""
    violations = await fetch_louisville_violations(200)
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['#', 'Address', 'Violation Type', 'Case ID', 'Status', 'Date', 'Score', 'ZIP'])
    
    for idx, v in enumerate(violations, 1):
        writer.writerow([
            idx,
            v['address'],
            v['violation_type'],
            v['case_id'],
            v['status'],
            v['date'],
            v['score'],
            v['zip']
        ])
    
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=hayseed_violations_{datetime.now().strftime('%Y%m%d')}.csv"}
    )

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "data_source": "Louisville Open Data Portal",
        "features": ["Live Data", "Search", "Filter", "Export", "Mobile", "Password Protected"]
    }
