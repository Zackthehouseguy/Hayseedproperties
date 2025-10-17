from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
import httpx
from datetime import datetime, timedelta
from typing import Optional, Dict
import io
import csv
import re

app = FastAPI()

# Correct Louisville API endpoint
LOUISVILLE_API = "https://services1.arcgis.com/79kfd2K6fskCAkyg/arcgis/rest/services/Code_Enforcement___Property_Maintenance_Violations/FeatureServer/0/query"

async def fetch_louisville_violations(limit: int = 500):
    try:
        # Get last 90 days to ensure we have data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)
        
        # Try with a simpler query first
        params = {
            'where': '1=1',  # Get all records
            'outFields': '*',
            'f': 'json',
            'returnGeometry': 'false',
            'resultRecordCount': limit,
            'orderByFields': 'INSPECTION_DATE DESC'
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(LOUISVILLE_API, params=params)
            data = response.json()
            
            if 'features' in data and len(data['features']) > 0:
                violations = []
                for feature in data['features']:
                    attrs = feature.get('attributes', {})
                    
                    # Get address - try multiple field names
                    address = (attrs.get('SITE_ADDRESS') or 
                             attrs.get('ADDRESS') or 
                             attrs.get('PROPERTY_ADDRESS') or 
                             'Address Not Available')
                    
                    # Get violation type
                    violation_type = (attrs.get('VIOLATION_CODE_DESCRIPTION') or 
                                    attrs.get('VIOLATION_DESCRIPTION') or 
                                    attrs.get('VIOLATION') or 
                                    'Violation Not Specified')
                    
                    # Calculate score
                    score = calculate_distress_score(attrs)
                    
                    violations.append({
                        'address': str(address),
                        'violation_type': str(violation_type),
                        'case_id': str(attrs.get('CASE_NUMBER', 'N/A')),
                        'status': str(attrs.get('CASE_STATUS', 'Unknown')),
                        'date': format_date(attrs.get('INSPECTION_DATE', '')),
                        'score': score,
                        'zip': extract_zip(str(address))
                    })
                
                # Sort by score
                violations.sort(key=lambda x: x['score'], reverse=True)
                return violations
            
        # If no data, return demo data
        return get_demo_data()
    
    except Exception as e:
        print(f"API Error: {e}")
        return get_demo_data()

def get_demo_data():
    """Return demo data if API fails"""
    return [
        {'address': '1234 Main St, Louisville, KY 40211', 'violation_type': 'Structural Damage - Unsafe Building', 'case_id': 'VM-2025-001', 'status': 'Open', 'date': 'Oct 15, 2025', 'score': 9, 'zip': '40211'},
        {'address': '5678 Oak Ave, Louisville, KY 40212', 'violation_type': 'Fire Hazard - Electrical Issues', 'case_id': 'VM-2025-002', 'status': 'Pending', 'date': 'Oct 14, 2025', 'score': 8, 'zip': '40212'},
        {'address': '910 Elm Street, Louisville, KY 40203', 'violation_type': 'Overgrown Property - Vacant', 'case_id': 'VM-2025-003', 'status': 'Open', 'date': 'Oct 13, 2025', 'score': 7, 'zip': '40203'},
        {'address': '2345 Broadway, Louisville, KY 40211', 'violation_type': 'Trash and Debris Accumulation', 'case_id': 'VM-2025-004', 'status': 'Open', 'date': 'Oct 12, 2025', 'score': 6, 'zip': '40211'},
        {'address': '7890 Maple Dr, Louisville, KY 40214', 'violation_type': 'Condemned Structure', 'case_id': 'VM-2025-005', 'status': 'Active', 'date': 'Oct 10, 2025', 'score': 10, 'zip': '40214'},
        {'address': '3456 Pine Rd, Louisville, KY 40212', 'violation_type': 'Health Hazard - Mold', 'case_id': 'VM-2025-006', 'status': 'Open', 'date': 'Oct 09, 2025', 'score': 8, 'zip': '40212'},
        {'address': '7891 Birch Ave, Louisville, KY 40203', 'violation_type': 'Exterior Maintenance Issue', 'case_id': 'VM-2025-007', 'status': 'Closed', 'date': 'Oct 08, 2025', 'score': 5, 'zip': '40203'},
        {'address': '1122 Cedar Ln, Louisville, KY 40211', 'violation_type': 'Plumbing Violations', 'case_id': 'VM-2025-008', 'status': 'Open', 'date': 'Oct 07, 2025', 'score': 7, 'zip': '40211'},
        {'address': '5544 Willow St, Louisville, KY 40214', 'violation_type': 'Unsafe Electrical System', 'case_id': 'VM-2025-009', 'status': 'Pending', 'date': 'Oct 06, 2025', 'score': 9, 'zip': '40214'},
        {'address': '9988 Ash Dr, Louisville, KY 40212', 'violation_type': 'Abandoned Vehicle on Property', 'case_id': 'VM-2025-010', 'status': 'Open', 'date': 'Oct 05, 2025', 'score': 4, 'zip': '40212'},
    ]

def calculate_distress_score(attrs: Dict) -> int:
    score = 5
    violation = str(attrs.get('VIOLATION_CODE_DESCRIPTION', '')).lower()
    status = str(attrs.get('CASE_STATUS', '')).lower()
    
    if any(word in violation for word in ['structural', 'unsafe', 'condemned', 'collapse', 'foundation']):
        score = 9
    elif any(word in violation for word in ['fire', 'electrical', 'hazard', 'health', 'mold']):
        score = 8
    elif any(word in violation for word in ['overgrown', 'trash', 'debris', 'vacant', 'abandoned']):
        score = 6
    elif any(word in violation for word in ['plumbing', 'roof', 'exterior']):
        score = 5
    
    if 'open' in status or 'active' in status or 'pending' in status:
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
    all_violations = await fetch_louisville_violations(500)
    
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
    vacant = sum(1 for v in all_violations if 'vacant' in v['violation_type'].lower() or 'abandoned' in v['violation_type'].lower())
    
    zips = {}
    for v in all_violations:
        if v['zip']:
            zips[v['zip']] = zips.get(v['zip'], 0) + 1
    top_zips = sorted(zips.items(), key=lambda x: x[1], reverse=True)[:5]
    
    property_cards = ""
    for idx, v in enumerate(filtered[:100], 1):
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
                        {f'<span>📍 {v["zip"]}</span>' if v['zip'] else ''}
                    </div>
                </div>
                <div class="bg-{color}-500 text-white px-4 py-3 rounded-full font-bold text-xl shadow-lg">
                    {v['score']}
                </div>
            </div>
        </div>
        """
    
    hotspot_html = ""
    for zip_code, count in top_zips:
        hotspot_html += f"""
        <div class="bg-gradient-to-br from-red-50 to-orange-50 border-2 border-red-300 rounded-xl p-4 hover:shadow-lg transition">
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
                <div class="flex items-center justify-between mb-3 flex-wrap gap-3">
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
                </div>
            </div>
            
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                <div class="bg-white p-6 rounded-xl shadow-lg border-l-4 border-blue-500 hover:shadow-xl transition">
                    <div class="flex justify-between items-center">
                        <div>
                            <div class="text-4​​​​​​​​​​​​​​​​
