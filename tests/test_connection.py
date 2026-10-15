"""
Diagnostic Test Script
Tests MT5 terminal connection and verifies all Gemini API Keys in the pool.
"""

from src.config_manager import ConfigManager
from src.connectors.mt5_connector import MT5Connector
from google import genai

def test_mt5():
    print("\n--- [1] Testing MT5 Terminal Connection ---")
    connector = MT5Connector()
    if not connector.connect():
        print("[NOTICE] Please verify MT5 terminal is open and 'Algo Trading' is enabled.")
        return False
    
    acc = connector.get_account_info()
    if acc:
        print(f"[OK] MT5 Connected! Login: {acc.login}, Server: {acc.server}, Balance: {acc.balance} {acc.currency}")
    connector.shutdown()
    return True

def test_gemini_keys(api_keys: list, model_name: str):
    print(f"\n--- [2] Testing Gemini API Keys Pool ({len(api_keys)} keys) with {model_name} ---")
    if not api_keys:
        print("[ERROR] No Gemini API keys found!")
        return

    for idx, key in enumerate(api_keys, 1):
        masked = key[:6] + "..." + key[-4:]
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model=model_name,
                contents="Say 'OK' in one word.",
            )
            print(f"[OK] Key #{idx} ({masked}): Active! Response: {response.text.strip()}")
        except Exception as e:
            print(f"[ERROR] Key #{idx} ({masked}): Failed ({e})")

if __name__ == "__main__":
    print("[DIAGNOSTIC] Running Diagnostics for ManusTrade...")
    try:
        config = ConfigManager.load("config.ini")
        test_mt5()
        test_gemini_keys(config.gemini.api_keys, config.gemini.model_name)
    except Exception as e:
        print(f"[ERROR] Diagnostic failed: {e}")
