import google.generativeai as genai

# PASTE YOUR KEY HERE
api_key = "AIzaSyAANSQuZsnKiCTZplanuv4C2n5Dn1Dqtok"

genai.configure(api_key=api_key)

print("Checking available models...")
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"- {m.name}")
except Exception as e:
    print(f"Error: {e}")