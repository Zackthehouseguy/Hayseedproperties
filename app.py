from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from apscheduler.schedulers.background import BackgroundScheduler
import io, csv, re, asyncio
import PyPDF2

app = FastAPI()

# Data storage
data_cache = {
    'violations': [],
    'lis_pendens': [],
    'tax_delinquent': [],
    'last_updated': {},
    'next_scrape': None
}

LOUISVILLE_API = "https://services1.arcgis.com/79kfd2K6fskCAkyg/arcgis/rest/services/Code_Enforcement___Property_Maintenance_Violations/FeatureServer/0/query"
JEFFERSON_DEEDS_URL = "https://search.jeffersondeeds.com"
JEFFERSON_TAX_PDF_REAL = "https://www.jeffersoncountyclerk.org/wp-content/uploads/2024/04/Real-Estate-Delinquent-Tax-Bills.pdf"

# ========== REAL SCRAPER 1: CODE VIOLATIONS ==========

async def scrape_violations(limit: int = 500):
    """Scrape Louisville violations from ArcGIS API - REAL DATA ONLY"""
    try:
        print("🏠 Scraping Code Violations...")
        params = {
            'where': '1=1',
            'outFields': '*',
            'f': 'json',
            'returnGeometry': 'false',
            'resultRecordCount': limit
        }
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
                print(f"   ✅ Found {len(violations)} violations")
                return violations
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print("   ⚠️  No violations data available")
    return []


# ========== REAL SCRAPER 2: LIS PENDENS ==========

async def scrape_lis_pendens():
    """Scrape Lis Pendens from Jefferson Deeds - REAL DATA ONLY"""
    try:
        print("📄 Scraping Lis Pendens...")
        
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            
            # Step 1: Get the search page to establish session
            search_url = f"{JEFFERSON_DEEDS_URL}/insttype.php"
            initial_response = await client.get(search_url)
            
            # Step 2: Prepare POST data for Lis Pendens search
            from_date = (datetime.now() - timedelta(days=365)).strftime('%m/%d/%Y')
            to_date = datetime.now().strftime('%m/%d/%Y')
            
            form_data = {
                'insttype': 'LIS PENDENS',
                'fromdate': from_date,
                'todate': to_date,
                'maxrecords': '500',
                'submit': 'Search'
            }
            
            # Step 3: Submit the search form
            results_response = await client.post(search_url, data=form_data)
            soup = BeautifulSoup(results_response.text, 'html.parser')
            
            # Step 4: Parse results table
            lis_pendens = []
            
            results_table = soup.find('table', {'class': 'results'}) or soup.find('table')
            
            if results_table:
                rows = results_table.find_all('tr')[1:]
                
                for row in rows[:100]:
                    try:
                        cols = row.find_all('td')
                        if len(cols) >= 4:
                            grantor = cols[0].get_text(strip=True)
                            grantee = cols[1].get_text(strip=True) if len(cols) > 1 else ''
                            legal_desc = cols[2].get_text(strip=True) if len(cols) > 2 else ''
                            date_filed = cols[3].get_text(strip=True) if len(cols) > 3 else ''
                            
                            address = extract_address_from_legal(legal_desc) or f"{grantor} property"
                            
                            lis_pendens.append({
                                'address': address,
                                'grantor': grantor,
                                'grantee': grantee,
                                'amount': 'See Document',
                                'date': date_filed,
                                'zip': extract_zip(address),
                                'score': 8,
                                'type': 'Lis Pendens'
                            })
                    except Exception as e:
                        continue
            
            if len(lis_pendens) > 0:
                print(f"   ✅ Found {len(lis_pendens)} lis pendens filings")
            else:
                print(f"   ⚠️  No lis pendens data found (check if form structure changed)")
            
            return lis_pendens
            
    except Exception as e:
        print(f"   ❌ Error scraping Lis Pendens: {e}")
        print(f"   ⚠️  No lis pendens data available")
        return []


# ========== REAL SCRAPER 3: TAX DELINQUENT ==========

async def scrape_tax_delinquent():
    """Scrape Tax Delinquent from PDF lists - REAL DATA ONLY"""
    try:
        print("💰 Scraping Tax Delinquent Properties...")
        
        tax_delinquent = []
        
        async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
            
            try:
                print("   📥 Downloading Real Estate Tax PDF...")
                pdf_response = await client.get(JEFFERSON_TAX_PDF_REAL)
                
                if pdf_response.status_code == 200:
                    pdf_bytes = io.BytesIO(pdf_response.content)
                    pdf_reader = PyPDF2.PdfReader(pdf_bytes)
                    
                    for page_num in range(min(10, len(pdf_reader.pages))):
                        page = pdf_reader.pages[page_num]
                        text = page.extract_text()
                        lines = text.split('\n')
                        
                        for line in lines:
                            if re.search(r'\$[\d,]+\.?\d*', line):
                                
                                amount_match = re.search(r'\$[\d,]+\.?\d*', line)
                                amount = amount_match.group() if amount_match else '$0'
                                
                                address_match = re.search(r'\d+\s+[A-Z\s]+(?:ST|AVE|DR|RD|LN|BLVD|CT)', line, re.IGNORECASE)
                                address = address_match.group() if address_match else line[:50]
                                
                                if len(address) > 10:
                                    tax_delinquent.append({
                                        'address': address.strip() + ', Louisville, KY',
                                        'amount': amount,
                                        'years': 'See Record',
                                        'zip': extract_zip(address),
                                        'score': 7,
                                        'source': 'Real Estate PDF'
                                    })
                                    
                                    if len(tax_delinquent) >= 100:
                                        break
                        
                        if len(tax_delinquent) >= 100:
                            break
                    
                    if len(tax_delinquent) > 0:
                        print(f"   ✅ Parsed {len(tax_delinquent)} properties from PDF")
                    else:
                        print(f"   ⚠️  PDF downloaded but no data extracted (check PDF format)")
                    
            except Exception as e:
                print(f"   ⚠️  PDF parsing error: {e}")
            
            return tax_delinquent[:100]
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        print(f"   ⚠️  No tax delinquent data available")
        return []


# ========== HELPER FUNCTIONS ==========

def extract_address_from_legal(legal_desc: str) -> str:
    """Extract street address from legal description"""
    match = re.search(r'\d+\s+[A-Z\s]+(?:STREET|ST|AVENUE|AVE|DRIVE|DR|ROAD|RD|LANE|LN|BOULEVARD|BLVD|COURT|CT)', 
                     legal_desc, re.IGNORECASE)
    if match:
        return match.group().strip() + ', Louisville, KY'
    return None

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


# ========== SCHEDULED SCRAPING ==========

async def run_all_scrapers():
    now = datetime.now()
    print(f"\n{'='*60}")
    print(f"🔄 SCRAPE START: {now.strftime('%Y-%m-%d %I:%M %p')}")
    print(f"{'='*60}")
    
    data_cache['violations'] = await scrape_violations(500)
    data_cache['lis_pendens'] = await scrape_lis_pendens()
    data_cache['tax_delinquent'] = await scrape_tax_delinquent()
    
    data_cache['last_updated'] = {
        'violations': now,
        'lis_pendens': now,
        'tax_delinquent': now
    }
    
    print(f"\n✅ SCRAPE COMPLETE:")
    print(f"   • Violations: {len(data_cache['violations'])} (REAL DATA)")
    print(f"   • Lis Pendens: {len(data_cache['lis_pendens'])} (REAL DATA)")
    print(f"   • Tax Delinquent: {len(data_cache['tax_delinquent'])} (REAL DATA)")
    print(f"{'='*60}\n")


def schedule_scrapers():
    scheduler = BackgroundScheduler()
    
    scheduler.add_job(lambda: asyncio.run(run_all_scrapers()), 'cron', hour=8, minute=0)
    scheduler.add_job(lambda: asyncio.run(run_all_scrapers()), 'cron', hour=14, minute=0)
    scheduler.add_job(lambda: asyncio.run(run_all_scrapers()), 'cron', hour=22, minute=0)
    
    scheduler.start()
    
    now = datetime.now()
    next_times = [now.replace(hour=h, minute=0, second=0) for h in [8, 14, 22]]
    future_times = [t for t in next_times if t > now]
    
    if future_times:
        data_cache['next_scrape'] = min(future_times)
    else:
        data_cache['next_scrape'] = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0)
    
    print(f"⏰ Next scrape: {data_cache['next_scrape'].strftime('%b %d, %I:%M %p')}")


@app.on_event("startup")
async def startup():
    print("🚀 Hayseed All-In-One Tool Starting...")
    print("⚠️  REAL DATA ONLY MODE - No fallback demo data")
    await run_all_scrapers()
    schedule_scrapers()
    print("✅ Hayseed Ready!")


# ========== WEB ROUTES ==========

@app.get("/", response_class=HTMLResponse)
async def home(data_type: str = "violations", search: Optional[str] = None):
    
    if data_type == "lis_pendens":
        data = data_cache['lis_pendens']
        title = "📄 Lis Pendens Filings"
        data_label = "Filings"
    elif data_type == "tax_delinquent":
        data = data_cache['tax_delinquent']
        title = "💰 Tax Delinquent Properties"
        data_label = "Properties"
    else:
        data = data_cache['violations']
        title = "🏠 Code Violations"
        data_label = "Violations"
    
    filtered = data
    if search:
        filtered = [d for d in filtered if search.lower() in d['address'].lower()]
    
    total = len(data)
    high = sum(1 for d in data if d.get('score', 0) >= 8)
    
    # Data status badge
    if total > 0:
        status_badge = f'<span class="bg-green-100 text-green-800 text-xs px-2 py-1 rounded">✅ {total} Real Records</span>'
    else:
        status_badge = '<span class="bg-red-100 text-red-800 text-xs px-2 py-1 rounded">⚠️ No Data Available</span>'
    
    cards = ""
    for i, item in enumerate(filtered[:100], 1):
        score = item.get('score', 5)
        c = 'red' if score >= 8 else 'orange' if score >= 6 else 'yellow'
        
        if data_type == "violations":
            detail = f"<div class='text-sm text-gray-600'>{item['violation_type']}</div><div class='text-xs text-gray-500'>📋 {item['case_id']} • {item['status']} • {item['date']}</div>"
        elif data_type == "lis_pendens":
            detail = f"<div class='text-sm text-gray-600'>{item.get('grantor', 'N/A')} → {item.get('grantee', 'N/A')}</div><div class='text-xs text-gray-500'>📅 Filed: {item['date']} • Amount: {item.get('amount', 'See Doc')}</div>"
        else:
            detail = f"<div class='text-sm text-gray-600'>Owed: {item['amount']}</div><div class='text-xs text-gray-500'>⏰ Delinquent: {item.get('years', 'N/A')}</div>"
        
        cards += f"<div class='border-l-4 border-{c}-500 p-4 bg-{c}-50 rounded mb-3'><div class='flex justify-between items-start'><div class='flex-1'><div class='font-bold'>#{i} {item['address']}</div>{detail}</div><div class='bg-{c}-500 text-white px-4 py-3 rounded-full font-bold text-xl ml-3'>{score}</div></div></div>"
    
    if not cards:
        cards = "<div class='bg-yellow-50 border-l-4 border-yellow-500 p-6 rounded'><p class='text-gray-700 font-semibold'>⚠️ No data available for this source</p><p class='text-sm text-gray-600 mt-2'>This could mean:</p><ul class='list-disc ml-6 mt-2 text-sm text-gray-600'><li>The scraper is still running (check back in a few minutes)</li><li>The source website structure has changed</li><li>There was a connection error</li></ul><p class='text-sm text-gray-600 mt-3'>Check the <a href='/health' class='text-blue-600 underline'>health endpoint</a> for details</p></div>"
    
    last_update = data_cache['last_updated'].get(data_type, datetime.now()).strftime('%b %d, %I:%M %p')
    next_scrape = data_cache.get('next_scrape', datetime.now()).strftime('%b %d, %I:%M %p')
    
    return f'''<!DOCTYPE html><html><head><title>Hayseed All-In-One</title><script src="https://cdn.tailwindcss.com"></script><meta name="viewport" content="width=device-width,initial-scale=1"></head><body class="bg-gray-50"><div class="max-w-7xl mx-auto p-4"><div class="bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-xl p-6 mb-6"><div class="flex justify-between items-center mb-3"><div><h1 class="text-3xl font-bold">🏠 Hayseed All-In-One</h1><p class="text-sm opacity-90">Real Data Only • Louisville/Jefferson County</p></div><a href="/export?type={data_type}" class="bg-white/20 hover:bg-white/30 px-4 py-2 rounded-lg text-sm transition">📥 Export CSV</a></div><div class="text-xs opacity-75">Last Updated: {last_update} • Next Scrape: {next_scrape}</div></div><div class="bg-white rounded-xl shadow-lg p-6 mb-6"><div class="flex justify-between items-center mb-4"><h2 class="text-xl font-bold">📊 Data Sources</h2>{status_badge}</div><div class="flex gap-3 flex-wrap"><a href="/?data_type=violations" class="px-4 py-2 rounded-lg transition {'bg-blue-600 text-white' if data_type == 'violations' else 'bg-gray-200 hover:bg-gray-300'}">🏠 Code Violations</a><a href="/?data_type=lis_pendens" class="px-4 py-2 rounded-lg transition {'bg-blue-600 text-white' if data_type == 'lis_pendens' else 'bg-gray-200 hover:bg-gray-300'}">📄 Lis Pendens</a><a href="/?data_type=tax_delinquent" class="px-4 py-2 rounded-lg transition {'bg-blue-600 text-white' if data_type == 'tax_delinquent' else 'bg-gray-200 hover:bg-gray-300'}">💰 Tax Delinquent</a></div></div><div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6"><div class="bg-white p-6 rounded-xl shadow-lg border-l-4 border-blue-500"><div class="text-4xl font-bold text-blue-600">{total}</div><div class="text-gray-600">Total {data_label}</div></div><div class="bg-white p-6 rounded-xl shadow-lg border-l-4 border-red-500"><div class="text-4xl font-bold text-red-600">{high}</div><div class="text-gray-600">High Priority (Score 8+)</div></div></div><div class="bg-white rounded-xl shadow-lg p-6 mb-6"><h2 class="text-xl font-bold mb-4">🔍 Search</h2><form method="get" class="flex gap-4"><input type="hidden" name="data_type" value="{data_type}"><input type="text" name="search" value="{search or ''}" placeholder="Search by address..." class="flex-1 px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"><button class="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg transition">Search</button></form><p class="mt-3 text-sm text-gray-600">Showing {len(filtered)} of {total} properties</p></div><div class="bg-white rounded-xl shadow-lg p-6"><h2 class="text-xl font-bold mb-4">{title}</h2>{cards}</div><div class="mt-6 text-center text-sm text-gray-500 bg-white rounded-xl p-4"><p class="mb-2"><a href="/mobile" class="text-blue-600 hover:underline">📱 Mobile View</a> • <a href="/health" class="text-blue-600 hover:underline">🏥 Health Check</a></p><p class="text-xs">Hayseed All-In-One • Auto-scraping 3x daily • 100% Real Data</p></div></div></body></html>'''


@app.get("/mobile", response_class=HTMLResponse)
async def mobile(data_type: str = "violations"):
    if data_type == "lis_pendens":
        data = data_cache['lis_pendens']
        title = "📄 Lis Pendens"
    elif data_type == "tax_delinquent":
        data = data_cache['tax_delinquent']
        title = "💰 Tax Delinquent"
    else:
        data = data_cache['violations']
        title = "🏠 Violations"
    
    critical = [d for d in data if d.get('score', 0) >= 8][:20]
    
    cards = ""
    for i, item in enumerate(critical, 1):
        cards += f"<div class='bg-red-50 border-l-4 border-red-500 p-4 rounded mb-3'><div class='flex justify-between items-start'><div class='flex-1'><div class='font-bold text-sm'>#{i} {item['address'][:40]}</div><div class='text-xs text-gray-600 mt-1'>{str(item.get('violation_type', item.get('amount', 'N/A')))[:50]}</div></div><div class='bg-red-500 text-white w-14 h-14 rounded-full flex items-center justify-center font-bold text-xl ml-3'>{item['score']}</div></div></div>"
    
    if not cards:
        cards = "<p class='text-gray-500 text-center py-8'>No high-priority items found</p>"
    
    return f'''<!DOCTYPE html><html><head><title>Hayseed Mobile</title><script src="https://cdn.tailwindcss.com"></script><meta name="viewport" content="width=device-width,initial-scale=1"></head><body class="bg-gray-50"><div class="bg-gradient-to-r from-blue-600 to-purple-600 text-white p-4 mb-4"><h1 class="text-2xl font-bold">🏠 Hayseed Mobile</h1><p class="text-sm">Real Data Only</p></div><div class="p-4 space-y-4"><div class="flex gap-2 overflow-x-auto"><a href="/mobile?data_type=violations" class="px-3 py-2 rounded-lg whitespace-nowrap text-sm {'bg-blue-600 text-white' if data_type == 'violations' else 'bg-gray-200'}">🏠 Violations</a><a href="/mobile?data_type=lis_pendens" class="px-3 py-2 rounded-lg whitespace-nowrap text-sm {'bg-blue-600 text-white' if data_type == 'lis_pendens' else 'bg-gray-200'}">📄 Lis Pendens</a><a href="/mobile?data_type=tax_delinquent" class="px-3 py-2 rounded-lg whitespace-nowrap text-sm {'bg-blue-600 text-white' if data_type == 'tax_delinquent' else 'bg-gray-200'}">💰 Tax</a></div><div class="grid grid-cols-2 gap-3"><div class="bg-red-500 rounded-xl p-4 text-white"><div class="text-3xl font-bold">{len(critical)}</div><div class="text-sm">Critical</div></div><div class="bg-blue-500 rounded-xl p-4 text-white"><div class="text-3xl font-bold">{len(data)}</div><div class="text-sm">Total</div></div></div><h2 class="font-bold text-lg">🚨 {title} - High Priority</h2>{cards}<a href="/export?type={data_type}" class="block bg-green-600 text-white text-center rounded-xl p-4 font-bold">📥 Export CSV</a><a href="/" class="block text-center text-blue-600 text-sm">← Desktop View</a></div></body></html>'''


@app.get("/export")
async def export(type: str = "violations"):
    data = data_cache.get(type, [])
    output = io.StringIO()
    writer = csv.writer(output)
    
    if type == "violations":
        writer.writerow(['#', 'Address', 'Violation', 'Case ID', 'Status', 'Date', 'Score', 'ZIP'])
        for i, v in enumerate(data, 1):
            writer.writerow([i, v['address'], v['violation_type'], v['case_id'], v['status'], v['date'], v['score'], v['zip']])
    elif type == "lis_pendens":
        writer.writerow(['#', 'Address', 'Grantor', 'Grantee', 'Amount', 'Filed Date', 'ZIP', 'Score'])
        for i, v in enumerate(data, 1):
            writer.writerow([i, v['address'], v.get('grantor',''), v.get('grantee',''), v.get('amount',''), v['date'], v['zip'], v['score']])
    else:
        writer.writerow(['#', 'Address', 'Amount Owed', 'Years Delinquent', 'ZIP', 'Score'])
        for i, v in enumerate(data, 1):
            writer.writerow([i, v['address'], v['amount'], v.get('years',''), v['zip'], v['score']])
    
    output.seek(0)
    filename = f"hayseed_{type}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "mode": "REAL DATA ONLY - No fallback demo data",
        "timestamp": datetime.now().isoformat(),
        "data_counts": {
            "violations": len(data_cache['violations']),
            "lis_pendens": len(data_cache['lis_pendens']),
            "tax_delinquent": len(data_cache['tax_delinquent'])
        },
        "last_updated": {k: v.isoformat() if v else None for k, v in data_cache.get('last_updated', {}).items()},
        "next_scrape": data_cache.get('next_scrape').isoformat() if data_cache.get('next_scrape') else None
    }
