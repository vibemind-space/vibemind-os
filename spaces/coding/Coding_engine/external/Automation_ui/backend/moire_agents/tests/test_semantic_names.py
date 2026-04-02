"""Test script for semantic names feature"""
import asyncio
import sys
sys.path.insert(0, '.')

from services.desktop_analyzer import DesktopAnalyzer

async def test():
    print('Testing semantic names...')
    analyzer = DesktopAnalyzer()
    
    try:
        await analyzer.connect()
        print('Connected to MoireServer')
        
        # Give server a moment to be ready
        await asyncio.sleep(1)
        
        result = await analyzer.scan_and_analyze(use_llm_names=True, timeout=120)
        
        # AnalysisResult is a dataclass, use to_dataframe() method
        if result.success:
            df = result.to_dataframe()  # Use method, not attribute
            print(f"\nSuccess: {len(df)} elements detected")
            
            if len(df) > 0:
                print(f"\nDataFrame columns: {list(df.columns)}")
                
                # Show sample with semantic names
                print("\nSample elements with semantic names:")
                cols = [c for c in ['name', 'category', 'ocr_text'] if c in df.columns]
                if cols:
                    print(df[cols].head(20).to_string())
                else:
                    print(df.head(20).to_string())
                
                # Show unique names
                if 'name' in df.columns:
                    print(f"\nUnique semantic names: {df['name'].nunique()}")
                    print(f"Sample names: {df['name'].head(10).tolist()}")
                    
                # Save to CSV for review
                df.to_csv('semantic_names_test.csv', index=False)
                print(f"\nSaved to semantic_names_test.csv")
            else:
                print("No elements detected!")
                print("Check that MoireServer is running and detection completed.")
        else:
            print(f"Failed: {result.error}")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await analyzer.disconnect()
        print("\nDisconnected")

if __name__ == '__main__':
    asyncio.run(test())