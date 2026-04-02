"""Test script for AgentDataFrame helper methods"""
import asyncio
import sys
sys.path.insert(0, '.')

from services.desktop_analyzer import DesktopAnalyzer

async def test():
    print("="*60)
    print("AgentDataFrame Test Suite")
    print("="*60)
    
    analyzer = DesktopAnalyzer()
    
    try:
        await analyzer.connect()
        print("\n✓ Connected to MoireServer")
        
        # Scan mit LLM
        print("\n📸 Scanning desktop...")
        result = await analyzer.scan_and_analyze(use_llm_names=True, timeout=120)
        
        if not result.success:
            print(f"FEHLER: {result.error}")
            return
        
        # AgentDataFrame erstellen
        adf = result.to_agent_dataframe()
        print(f"\n✓ AgentDataFrame erstellt: {len(adf)} Elemente")
        print(f"   Summary: {adf.summary()}")
        
        # ==================== Test 1: O(1) Lookups ====================
        print("\n" + "="*40)
        print("Test 1: O(1) Lookups")
        print("="*40)
        
        # Teste __getitem__
        test_names = ["Chrome", "Save", "button", "input"]
        for name in test_names:
            elem = adf[name]
            if elem:
                print(f"  df['{name}'] -> {elem.name} @({elem.center_x},{elem.center_y})")
            else:
                # Fuzzy-Suche als Fallback
                found = adf.search(name, threshold=0.5)
                if found:
                    print(f"  df['{name}'] not found, but search found: {found[0].name}")
                else:
                    print(f"  df['{name}'] -> NOT FOUND")
        
        # Teste click()
        print("\n  click() Tests:")
        buttons = adf.buttons()
        if buttons:
            first_btn = buttons[0]
            coords = adf.click(first_btn.name)
            print(f"    click('{first_btn.name}') -> {coords}")
        
        # ==================== Test 2: Category Filters ====================
        print("\n" + "="*40)
        print("Test 2: Category Filters")
        print("="*40)
        
        print(f"  Categories: {adf.categories()}")
        print(f"  buttons(): {len(adf.buttons())} elements")
        print(f"  inputs(): {len(adf.inputs())} elements")
        print(f"  icons(): {len(adf.icons())} elements")
        print(f"  text_elements(): {len(adf.text_elements())} elements")
        print(f"  links(): {len(adf.links())} elements")
        print(f"  containers(): {len(adf.containers())} elements")
        
        # ==================== Test 3: Text Search ====================
        print("\n" + "="*40)
        print("Test 3: Text Search")
        print("="*40)
        
        # Test by_text
        search_terms = ["Save", "File", "Edit"]
        for term in search_terms:
            found = adf.by_text(term)
            if found:
                print(f"  by_text('{term}'): {[e.name for e in found[:3]]}")
            else:
                print(f"  by_text('{term}'): no results")
        
        # Test fuzzy search
        print("\n  Fuzzy search() Tests:")
        fuzzy_terms = ["chrom", "save", "window"]
        for term in fuzzy_terms:
            found = adf.search(term, threshold=0.4)
            if found:
                print(f"    search('{term}'): {[e.name for e in found[:3]]}")
            else:
                print(f"    search('{term}'): no results")
        
        # ==================== Test 4: Spatial Queries ====================
        print("\n" + "="*40)
        print("Test 4: Spatial Queries")
        print("="*40)
        
        # Test at_point
        test_points = [(100, 100), (500, 500), (960, 540)]
        for x, y in test_points:
            elems = adf.at_point(x, y)
            if elems:
                print(f"  at_point({x},{y}): {[e.name for e in elems[:2]]}")
            else:
                print(f"  at_point({x},{y}): no elements")
        
        # Test in_region
        print("\n  Region Tests:")
        toolbar = adf.toolbar()
        print(f"    toolbar(): {len(toolbar)} elements in top 80px")
        
        taskbar = adf.taskbar()
        print(f"    taskbar(): {len(taskbar)} elements in bottom 60px")
        
        center = adf.in_region(700, 400, 500, 300)
        print(f"    center region: {len(center)} elements")
        
        # Test nearest
        print("\n  Nearest Tests:")
        nearest = adf.nearest(960, 540)
        if nearest:
            print(f"    nearest(960,540): {nearest.name} @({nearest.center_x},{nearest.center_y})")
        
        nearest_btn = adf.nearest(960, 540, category='button')
        if nearest_btn:
            print(f"    nearest button: {nearest_btn.name}")
        
        # ==================== Test 5: LLM Context ====================
        print("\n" + "="*40)
        print("Test 5: LLM Context Generation")
        print("="*40)
        
        context = adf.to_context(max_elements=10)
        print(f"  to_context(max=10):")
        for line in context.split('\n')[:15]:
            print(f"    {line}")
        
        # Test JSON output
        json_out = adf.to_json(max_elements=3)
        print(f"\n  to_json(max=3): {len(json_out)} bytes")
        
        # ==================== Test 6: Performance ====================
        print("\n" + "="*40)
        print("Test 6: Performance")
        print("="*40)
        
        import time
        
        # O(1) Lookup performance
        name_to_find = adf.all_elements[0].name if adf.all_elements else "test"
        start = time.perf_counter()
        for _ in range(10000):
            _ = adf[name_to_find]
        elapsed = (time.perf_counter() - start) * 1000
        print(f"  10000 x df[name] lookups: {elapsed:.2f}ms ({elapsed/10:.4f}ms per lookup)")
        
        # Category filter performance
        start = time.perf_counter()
        for _ in range(10000):
            _ = adf.buttons()
        elapsed = (time.perf_counter() - start) * 1000
        print(f"  10000 x buttons() calls: {elapsed:.2f}ms")
        
        # Spatial query performance
        start = time.perf_counter()
        for _ in range(1000):
            _ = adf.at_point(960, 540)
        elapsed = (time.perf_counter() - start) * 1000
        print(f"  1000 x at_point() calls: {elapsed:.2f}ms")
        
        # ==================== Summary ====================
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        print(f"  Total elements: {len(adf)}")
        print(f"  Categories: {len(adf.categories())}")
        print(f"  Unique names indexed: {len(adf._by_name)}")
        print(f"  Texts indexed: {len(adf._by_text)}")
        print(f"  Grid cells used: {len(adf._grid)}")
        print("\n✅ All tests completed!")
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await analyzer.disconnect()
        print("\nDisconnected")

if __name__ == '__main__':
    asyncio.run(test())