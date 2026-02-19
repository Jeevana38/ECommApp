import requests


class MarketplaceClient:
    """
    Base REST client for Buyer and Seller CLI (PA2).
    """

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session_id = None

    # ---------------------------------
    # Core REST sender
    # ---------------------------------

    def _post(self, endpoint: str, payload: dict, require_session: bool = False):
        """
        Sends POST request to REST server.

        Args:
            endpoint: REST endpoint path
            payload: JSON body
            require_session: automatically attach session_token
        """

        if require_session:
            if not self.session_id:
                raise Exception("You must login first.")
            payload = dict(payload)
            payload["session_token"] = self.session_id

        url = f"{self.base_url}/{endpoint}"

        try:
            response = requests.post(
                url,
                json=payload,
                timeout=10  # important for performance testing
            )
        except requests.exceptions.RequestException as e:
            raise Exception(f"Connection error: {e}")

        if response.status_code != 200:
            raise Exception(
                f"Request failed ({response.status_code}): {response.text}"
            )

        return response.json()

    # ---------------------------------
    # Session Handling
    # ---------------------------------

    def set_session(self, session_id: str):
        self.session_id = session_id

    def clear_session(self):
        self.session_id = None
