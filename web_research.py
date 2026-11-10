import requests
import json

class WebResearchModule:
    """Professional Search Module using Serper.dev API for guaranteed data extraction."""

    def __init__(self):
        self.api_key = "92be9d6f74ddae069b4b8563bf6b4c5217b7c20c"
        self.url = "https://google.serper.dev/search"

    def fast_search(self, query):
        """Fetches a precise snippet from the web using the Serper API."""
        try:
            payload = json.dumps({"q": query})
            headers = {
                'X-API-KEY': self.api_key,
                'Content-Type': 'application/json'
            }

            response = requests.post(self.url, headers=headers, data=payload, timeout=5)

            if response.status_code != 200:
                return "I encountered a synchronization error with the global archives, sir."

            data = response.json()

            # Try to get the "answer box" first (the instant answer Google gives)
            if "answerBox" in data and data["answerBox"]:
                answer = data["answerBox"].get("answer") or data["answerBox"].get("snippet")
                if answer:
                    return answer

            # Fallback to the first organic search result
            if "organic" in data and data["organic"]:
                result = data["organic"][0].get("snippet")
                if result:
                    if len(result) > 200:
                        result = result[:197] + "..."
                    return result

            return "I found the topic, but no concise summary was available in the archives, sir."

        except Exception as e:
            print(f"Serper API Error: {e}")
            return "My connection to the global network was interrupted, sir."

# Initialize the researcher
researcher = WebResearchModule()
