"""
Test-Skript für den HTTP Bridge Server
"""

import asyncio
import aiohttp
import json

BASE_URL = "http://localhost:8766"

async def test_status():
    """Test GET /status"""
    print("=" * 50)
    print("Test 1: GET /status")
    print("=" * 50)
    
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/status") as resp:
            status = resp.status
            data = await resp.json()
            print(f"Status: {status}")
            print(f"Response: {json.dumps(data, indent=2)}")
            return status == 200

async def test_classify_batch():
    """Test POST /classify_batch"""
    print("\n" + "=" * 50)
    print("Test 2: POST /classify_batch")
    print("=" * 50)
    
    payload = {
        "batchId": "test_batch_001",
        "icons": [
            {
                "boxId": "icon_1",
                "cropBase64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                "cnnCategory": "button",
                "cnnConfidence": 0.85
            },
            {
                "boxId": "icon_2",
                "cropBase64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAEAwH/xfHZxAAAAABJRU5ErkJggg==",
                "cnnCategory": "text_field",
                "cnnConfidence": 0.72,
                "ocrText": "Submit"
            }
        ]
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{BASE_URL}/classify_batch",
            json=payload,
            headers={"Content-Type": "application/json"}
        ) as resp:
            status = resp.status
            data = await resp.json()
            print(f"Status: {status}")
            print(f"Response: {json.dumps(data, indent=2)}")
            return status == 200

async def test_stats():
    """Test GET /stats"""
    print("\n" + "=" * 50)
    print("Test 3: GET /stats")
    print("=" * 50)
    
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/stats") as resp:
            status = resp.status
            data = await resp.json()
            print(f"Status: {status}")
            print(f"Response: {json.dumps(data, indent=2)}")
            return status == 200

async def main():
    print("\n" + "#" * 60)
    print("# MoireTracker HTTP Bridge - Test Suite")
    print("#" * 60 + "\n")
    
    results = []
    
    # Test 1: Status
    results.append(("GET /status", await test_status()))
    
    # Test 2: Classify Batch
    results.append(("POST /classify_batch", await test_classify_batch()))
    
    # Test 3: Stats
    results.append(("GET /stats", await test_stats()))
    
    # Summary
    print("\n" + "=" * 50)
    print("ZUSAMMENFASSUNG")
    print("=" * 50)
    
    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("✓ Alle Tests bestanden!")
    else:
        print("✗ Einige Tests fehlgeschlagen!")
    
    return all_passed

if __name__ == "__main__":
    asyncio.run(main())