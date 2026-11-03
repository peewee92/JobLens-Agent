"""Journal each actual HTTP attempt; never permit implicit replay."""
import httpx


class JournaledTransport(httpx.BaseTransport):
    def __init__(self, journal, action_id, inner):
        self.journal, self.action_id, self.inner = journal, action_id, inner

    def handle_request(self, request):
        self.journal.begin_attempt(self.action_id)
        response = self.inner.handle_request(request)
        response.read()
        try:
            payload = response.json()
            usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
        except (ValueError, UnicodeError):
            usage = {}
        self.journal.received(self.action_id, response.status_code, usage if isinstance(usage, dict) else {})
        return response

    def close(self):
        self.inner.close()
