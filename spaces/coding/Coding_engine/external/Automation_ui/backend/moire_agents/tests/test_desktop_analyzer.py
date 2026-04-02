"""Test script for DesktopAnalyzer - Debug Version"""
import asyncio
import sys
import logging
sys.path.insert(0, '.')

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def test_direct_websocket():
    """Test direkter WebSocket-Kommunikation"""
    from bridge.websocket_client import MoireWebSocketClient
    
    print("="*60)
    print("TEST 1: Direkter WebSocket Test")
    print("="*60)
    
    client = MoireWebSocketClient()
    
    # Event Handler für Debug
    def on_state_changed(event):
        print(f"\n>>> STATE_CHANGED RECEIVED! v{event.version}, {len(event.ui_context.elements)} elements\n")
    
    client.on_state_changed(on_state_changed)
    
    # Connect
    print("Connecting...")
    connected = await client.connect()
    print(f"Connected: {connected}")
    
    if not connected:
        print("FEHLER: Nicht verbunden!")
        return
    
    # Warte kurz damit Background Receiver läuft
    await asyncio.sleep(1)
    
    # Capture starten
    print("\nStarting capture...")
    result = await client.capture_and_wait_for_complete(timeout=30.0)
    
    print(f"\n{'='*60}")
    print("ERGEBNIS:")
    print(f"  Success: {result.success}")
    print(f"  Boxes: {result.boxes_count}")
    print(f"  Texts: {result.texts_count}")
    print(f"  Error: {result.error}")
    print(f"  Time: {result.processing_time_ms:.0f}ms")
    
    if result.ui_context:
        print(f"  Elements: {len(result.ui_context.elements)}")
        texts = [e.text for e in result.ui_context.elements if e.text][:5]
        print(f"  Sample texts: {texts}")
    
    # Disconnect
    await client.disconnect()
    print("\nDisconnected")

async def test_analyzer_simple():
    """Test DesktopAnalyzer ohne LLM"""
    from services.desktop_analyzer import DesktopAnalyzer
    
    print("\n" + "="*60)
    print("TEST 2: DesktopAnalyzer (ohne LLM)")
    print("="*60)
    
    async with DesktopAnalyzer() as analyzer:
        print("Scanning...")
        result = await analyzer.scan_and_analyze(use_llm_names=False, timeout=30.0)
        
        print(f"\n{'='*60}")
        print(f"Success: {result.success}")
        print(f"Total Elements: {result.total_elements}")
        print(f"Error: {result.error}")
        
        if result.success and result.elements:
            df = result.to_dataframe()
            print(f"\nDataFrame shape: {df.shape}")
            print(df.head(10).to_string())
            
            # Save
            df.to_csv('desktop_elements.csv', index=False)
            print("\nSaved to desktop_elements.csv")
        else:
            print("Keine Elemente - DataFrame leer")

if __name__ == '__main__':
    # Run both tests
    print("\n" + "="*60)
    print("DESKTOP ANALYZER DEBUG TEST")
    print("="*60 + "\n")
    
    # Test 1: Direct WebSocket
    asyncio.run(test_direct_websocket())
    
    # Short pause
    print("\n\nWarte 2 Sekunden...\n")
    import time
    time.sleep(2)
    
    # Test 2: Full Analyzer
    asyncio.run(test_analyzer_simple())