#!/usr/bin/env python
"""Test script to verify Arete-19B integration"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

try:
    from backend import ARETE_AVAILABLE, load_arete_model, generate_with_arete
    print(f"[Test] Arete-19B available: {ARETE_AVAILABLE}")

    if ARETE_AVAILABLE:
        print("[Test] Loading Arete-19B model...")
        success = load_arete_model()
        if success:
            print("[Test] Arete-19B model loaded successfully!")

            # Test with a simple query
            test_query = "Explain quantum computing in simple terms"
            print(f"[Test] Testing query: {test_query}")
            response = generate_with_arete(test_query)
            if response and len(response) > 20:
                print("[Test] Arete-19B response generated successfully!")
                print(f"[Response preview] {response[:200]}...")
            else:
                print("[Test] Arete-19B returned insufficient response")
        else:
            print("[Test] Failed to load Arete-19B model")
    else:
        print("[Test] Arete-19B not available - using cloud Gemini only")

except Exception as e:
    print(f"[Test] Error: {e}")
    import traceback
    traceback.print_exc()