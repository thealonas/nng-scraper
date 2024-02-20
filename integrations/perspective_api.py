import asyncio

import sentry_sdk
from googleapiclient import discovery
from googleapiclient.errors import HttpError


class PerspectiveApi:
    DELAY_IN_SECONDS = 1

    def __init__(self, api_key: str):
        self.client = discovery.build(
            "commentanalyzer",
            "v1alpha1",
            developerKey=api_key,
            discoveryServiceUrl="https://commentanalyzer.googleapis.com/$discovery/rest?version=v1alpha1",
            static_discovery=False,
        )

    @staticmethod
    def to_fixed(value: float, digits=4) -> float:
        return float(f"{value:.{digits}f}")

    def analyze_toxicity(self, text: str) -> float:
        analyze_request = {
            "comment": {"text": text},
            "requestedAttributes": {"TOXICITY": {}},
            "languages": ["ru"],
        }

        try:
            response = self.client.comments().analyze(body=analyze_request).execute()
            types: dict = response.get("attributeScores")
            return self.to_fixed(types.get("TOXICITY").get("summaryScore").get("value"))
        except AttributeError as attribute:
            sentry_sdk.capture_exception(attribute)
            return 0
        except HttpError as http:
            if http.status_code != 429:
                sentry_sdk.capture_exception(http)
                return 0
            asyncio.run(asyncio.sleep(1))
            return self.analyze_toxicity(text)
