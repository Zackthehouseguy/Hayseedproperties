from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import httpx
from datetime import datetime, timedelta
from typing import List, Dict
import os

app = FastAPI()

# Louisville API endpoint
LOUISVILLE_API = "https://services1.arcgis.com/79kfd2K6fskCAkyg/arcgis/rest/services/Code_Enforcement___Property_Maintenance_Violations/FeatureServer/0/query"

async def fetch_louisville_violations():
    """Fetch real violations from Louisville Open Data"""
    try:
        # Calculate date range (last 30 days)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        # Format dates for API
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        
        # API parameters
        params = {
            'where': f"INSPECTION_DATE >= timestamp '{start_str} 00:00:00' AND INSPECTION_DATE <= timestamp '{end_str} 23:59:59'",
            'outFields': '*',
            'f': 'json',
            'returnGeometry': 'false',
            'resultRecordCount': 100  # Get top 100
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(LOUISVILLE_API, params=params)
            data = response.json()
            
            if 'features' in data:
                violations = []
                for feature in data['features']:
                    attrs = feature.get('attributes', {})
                    
                    # Calculate simple distress score
                    score = calculate_distress_score(attrs)
                    
                    violations.append({
                        'address': attrs.get('SITE_ADDRESS', 'Unknown Address'),
                        'violation_type': attrs.get('VIOLATION_CODE_DESCRIPTION', 'Unknown'),
                        'case_id': attrs.get('CASE_NUMBER', 'N/A'),
                        'status': attrs.get('CASE_STATUS', 'Open'),
                        'date': attrs.get('INSPECTION_DATE', ''),
                        'score': score
                    })
                
                # Sort by score (highest first)
                violations.sort(key=lambda x: x['score'], reverse=True)
                return violations[:50]  # Return top 50
        
        return []
    
    except Exception as e:
        print(f"Error fetching Louisville data: {e}")
        return []

def calculate_distress_score(attrs: Dict) -> int:
    """Calculate distress score 1-10 based on violation"""
    score = 5  # Base score
    
    violation = str(attrs.get('VIOLATION_CODE_DESCRIPTION', '')).lower()
    status = str(attrs.get('CASE_STATUS', '')).lower()
    
    # Increase score for severe violations
    if any(word in violation for word in ['structural', 'unsafe', 'condemned', 'collapse']):
        score = 9
    elif any(word in violation for word in ['fire', 'electrical', 'hazard', 'health']):
        score = 8
    elif any(word in violation for word in ['overgrown', 'trash', 'debris', 'vacant']):
        score = 6
    
    # Increase if case is open/active
    if 'open' in status or 'active' in status:
        score = min(score + 1, 10)
    
    return score

@app.get("/", response_class=HTMLResponse)
async def home():
    """Main dashboard with REAL Louisville data"""
    
    # Fetch real violations
    violations = await fetch_louisville_violations()
    
    # Calculate stats
    total = len(violations)
    high_distress = sum(1 for v in violations if v['score'] >= 8)
    vacant = sum(1 for v in violations if 'vacant' in v['violation_type'].lower())
    
    # Generate property cards HTML
    property_cards = ""
    for v in violations[:20]:  # Show top 20
        color = 'red' if v['score'] >= 8 else 'orange' if v['score'] >= 6 else 'yellow'
        
        property_cards += f"""
        <div class="border-l-4 border-{color}-500 p-4 bg-{color}-50 rounded">
            <div class="flex justify-between items-start">
                <div>
                    <div class="font-bold">{v['address']}</div>
                    <div class="text-sm text-gray-600">{v['violation_type']} • Case: {v['case_id']}</div>
                    <div class="text-xs text-gray-500 mt-1">Status: {v['status']}</div>
                </div>
                <div class="bg-{color}-500 text-white px-3 py-1 rounded-full font-bold">{v['score']}</div>
            </div>
        </div>
        """
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Hayseed Properties - Live Data</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <meta name="viewport" content="width=device-width, initial-scale=1">
    </head>
    <body class="bg-gray-50">
        <div class="max-w-7xl mx-auto p-6">
            <div class="bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-xl p-6 mb-6">
                <h1 class="text-3xl font-bold mb-2">🏠 Hayseed Properties</h1>
                <p class="text-sm opacity-90">Live Louisville Property Violations - Last 30 Days</p>
                <p class="text-xs opacity-75 mt-2">📡 Connected to Louisville Open Data Portal</p>
            </div>
            
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                <div class="bg-white p-6 rounded-lg shadow-lg border-l-4 border-blue-500">
                    <div class="text-3xl font-bold text-blue-600">{total}</div>
                    <div class="text-gray-600">Total Violations (30 days)</div>
                </div>
                <div class="bg-white p-6 rounded-lg shadow-lg border-l-4 border-red-500">
                    <div class="text-3xl font-bold text-red-600">{high_distress}</div>
                    <div class="text-gray-600">High Distress (Score ≥8)</div>
                </div>
                <div class="bg-white p-6 rounded-lg shadow-lg border-l-4 border-orange-500">
                    <div class="text-3xl font-bold text-orange-600">{vacant}</div>
                    <div class="text-gray-600">Potentially Vacant</div>
                </div>
            </div>

            <div class="bg-white rounded-lg shadow-lg p-6">
                <div class="flex justify-between items-center mb-4">
                    <h2 class="text-xl font-bold">Top Priority Properties</h2>
                    <span class="text-sm text-gray-500">Showing top 20 of {total}</span>
                </div>
                <div class="space-y-3">
                    {property_cards}
                </div>
            </div>

            <div class="mt-6 text-center text-sm text-gray-500">
                <p>🔄 Data refreshes every time you load the page</p>
                <p>Last updated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
            </div>
        </div>
    </body>
    </html>
    """

@app.get("/mobile", response_class=HTMLResponse)
async def mobile():
    """Mobile app with REAL data"""
    violations = await fetch_louisville_violations()
    
    # Get top 5 critical
    critical = [v for v in violations if v['score'] >= 8][:5]
    
    property_cards = ""
    for v in critical:
        property_cards += f"""
        <div class="bg-red-50 border-l-4 border-red-500 p-4 rounded">
            <div class="flex justify-between items-center mb-2">
                <div>
                    <div class="font-bold">{v['address']}</div>
                    <div class="text-sm text-gray-600">{v['violation_type']}</div>
                </div>
                <div class="bg-red-500 text-white w-12 h-12 rounded-full flex items-center justify-center font-bold">
                    {v['score']}
                </div>
            </div>
        </div>
        """
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Hayseed Mobile - Live</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-50">
        <div class="bg-gradient-to-r from-blue-600 to-purple-600 text-white p-4">
            <h1 class="text-2xl font-bold">🏠 Hayseed Mobile</h1>
            <p class="text-sm opacity-90">Field Inspector • Live Data</p>
        </div>
        
        <div class="p-4 space-y-4">
            <div class="bg-green-50 border-l-4 border-green-500 p-3 rounded">
                <div class="flex items-center gap-2">
                    <span class="text-green-600">📡</span>
                    <span class="text-sm font-medium text-green-800">Connected to Louisville API</span>
                </div>
            </div>

            <div class="grid grid-cols-2 gap-3">
                <div class="bg-gradient-to-br from-red-500 to-red-600 rounded-xl p-4 text-white">
                    <div class="text-3xl font-bold mb-1">{len(critical)}</div>
                    <div class="text-sm opacity-90">Critical Properties</div>
                </div>
                <div class="bg-gradient-to-br from-blue-500 to-blue-600 rounded-xl p-4 text-white">
                    <div class="text-3xl font-bold mb-1">{len(violations)}</div>
                    <div class="text-sm opacity-90">Total Violations</div>
                </div>
            </div>

            <h2 class="font-bold text-gray-800 mt-4">Critical Properties</h2>
            <div class="space-y-3">
                {property_cards}
            </div>

            <div class="mt-4 text-center text-xs text-gray-500">
                Last updated: {datetime.now().strftime('%I:%M %p')}
            </div>
        </div>
    </body>
    </html>
    """

@app.get("/health")
async def health():
    return {"status": "healthy", "data_source": "Louisville Open Data Portal"}
