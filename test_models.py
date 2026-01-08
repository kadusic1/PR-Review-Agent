import os
import time
from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")


def test_model(name, model_id, prompt):
    print(f"\nTestiram: {name} ({model_id})...")
    try:
        llm = ChatGroq(temperature=0, model_name=model_id, api_key=api_key)
        start = time.time()
        response = llm.invoke(prompt)
        duration = time.time() - start

        print(f"USPJEH ({duration:.2f}s)")
        print(f"Odgovor: {response.content}")
        return True
    except Exception as e:
        print(f"GRESKA na {name}: {e}")
        return False


# --- GLAVNI DIO ---
if __name__ == "__main__":
    if not api_key:
        print("Nema API kljuca!")
        exit(1)

    
    test_model(
        "MOZAK (Llama 3.3 70B)",
        "llama-3.3-70b-versatile",
        "Napisi jednu kratku recenicu o kvantnoj fizici.",
    )

    
    test_model(
        "BRZINAC (Llama 3.1 8B)",
        "llama-3.1-8b-instant",
        "Napisi samo jednu rijec: Pozdrav.",
    )
