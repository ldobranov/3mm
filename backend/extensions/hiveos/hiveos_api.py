import requests
import time
import logging

logger = logging.getLogger("hiveos_api")

class HiveOSAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def _request_with_retries(self, method, url, retries=5, **kwargs):
        for attempt in range(retries):
            try:
                response = requests.request(method, url, headers=self.headers, **kwargs)
                if response.status_code == 521:
                    logger.warning(f"HiveOS API returned 521, attempt {attempt + 1}/{retries}")
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                if attempt == retries - 1:
                    logger.error(f"Request failed after {retries} attempts: {e}")
                    raise
                else:
                    logger.warning(f"Retrying request, attempt {attempt + 1}/{retries}")
                    time.sleep(2 ** attempt)  # Exponential backoff

    def get(self, url, retries=5, **kwargs):
        return self._request_with_retries("GET", url, retries, **kwargs)

    def post(self, url, retries=5, **kwargs):
        return self._request_with_retries("POST", url, retries, **kwargs)

# Example usage:
# api = HiveOSAPI(api_key="your_api_key")
# response = api.get("https://api2.hiveos.farm/api/v2/farms")
# print(response.json())
