from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Hayseed Properties</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-50">
        <div class="max-w-7xl mx-auto p-6">
            <h1 class="text-3xl font-bold mb-6">🏠 Hayseed Properties Dashboard</h1>
            
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                <div class="bg-white p-6 rounded-lg shadow">
                    <div class="text-3xl font-bold text-red-600">42</div>
                    <div class="text-gray-600">High Distress Properties</div>
                </div>
                <div class="bg-white p-6 rounded-lg shadow">
                    <div class="text-3xl font-bold text-blue-600">218</div>
                    <div class="text-gray-600">Total Properties</div>
                </div>
                <div class="bg-white p-6 rounded-lg shadow">
                    <div class="text-3xl font-bold text-orange-600">18</div>
                    <div class="text-gray-600">Potentially Vacant</div>
                </div>
            </div>

            <div class="bg-white rounded-lg shadow p-6">
                <h2 class="text-xl font-bold mb-4">Top Priority Properties</h2>
                <div class="space-y-3">
                    <div class="border-l-4 border-red-500 p-4 bg-red-50">
                        <div class="flex justify-between items-start">
                            <div>
                                <div class="font-bold">1234 Main St, Louisville, KY</div>
                                <div class="text-sm text-gray-600">Structural Damage • Case: VM-2025-001</div>
                            </div>
                            <div class="bg-red-500 text-white px-3 py-1 rounded-full font-bold">9</div>
                        </div>
                    </div>
                    <div class="border-l-4 border-orange-500 p-4 bg-orange-50">
                        <div class="flex justify-between items-start">
                            <div>
                                <div class="font-bold">5678 Oak Ave, Louisville, KY</div>
                                <div class="text-sm text-gray-600">Fire Hazard • Case: VM-2025-002</div>
                            </div>
                            <div class="bg-orange-500 text-white px-3 py-1 rounded-full font-bold">8</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

@app.get("/mobile", response_class=HTMLResponse)
async def mobile():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Hayseed Mobile</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-50">
        <div class="bg-blue-600 text-white p-4">
            <h1 class="text-2xl font-bold">🏠 Hayseed Mobile</h1>
            <p class="text-sm">Field Inspector</p>
        </div>
        
        <div class="p-4 space-y-4">
            <div class="grid grid-cols-2 gap-3">
                <div class="bg-gradient-to-br from-red-500 to-red-600 rounded-xl p-4 text-white">
                    <div class="text-3xl font-bold mb-1">5</div>
                    <div class="text-sm opacity-90">Critical Nearby</div>
                </div>
                <div class="bg-gradient-to-br from-blue-500 to-blue-600 rounded-xl p-4 text-white">
                    <div class="text-3xl font-bold mb-1">12</div>
                    <div class="text-sm opacity-90">Inspections Today</div>
                </div>
            </div>

            <div class="bg-red-50 border-l-4 border-red-500 p-4 rounded">
                <div class="flex justify-between items-center mb-2">
                    <div>
                        <div class="font-bold">1234 Main St</div>
                        <div class="text-sm text-gray-600">0.2 mi away</div>
                    </div>
                    <div class="bg-red-500 text-white w-12 h-12 rounded-full flex items-center justify-center font-bold">
                        9
                    </div>
                </div>
                <div class="text-sm text-gray-700">Structural Damage</div>
            </div>
            
            <button class="w-full bg-blue-600 text-white p-4 rounded-lg font-semibold">
                📷 Start Inspection
            </button>
            
            <button class="w-full bg-green-600 text-white p-4 rounded-lg font-semibold">
                📞 Call Dispatch
            </button>
        </div>
    </body>
    </html>
    """

@app.get("/health")
async def health():
    return {"status": "healthy"}
