import os
from typing import List

from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel, Field

from agents.gemini_retry import call_gemini_with_retry


load_dotenv()


class TestScenario(BaseModel):
    id: str
    title: str
    description: str

    scenario_type: str = Field(
        description="positive, negative, or edge"
    )

    priority: str = Field(
        description="high, medium, or low"
    )

    steps: List[str]
    expected_result: str


class RequirementAnalysis(BaseModel):
    feature: str
    summary: str
    scenarios: List[TestScenario]


class RequirementAgent:

    def __init__(self, client=None):

        if client is not None:
            self.client = client
            return

        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not configured in .env"
            )

        self.client = genai.Client(
            api_key=api_key
        )

    def analyze(
        self,
        user_story: str
    ) -> RequirementAnalysis:

        prompt = f"""
You are a Senior QA Automation Engineer.

Analyze the software requirement below.

Your job is to identify only what is supported by the supplied requirement:

1. The main feature.
2. A concise requirement summary.
3. The smallest set of precise test scenarios needed to cover the stated
   acceptance criteria.
4. Priority, clear test steps, and expected results for each scenario.

Important rules:

- Do NOT generate Playwright code.
- Do NOT generate Python code.
- Treat acceptance criteria as authoritative. Every scenario, step, and
  expected result must be directly traceable to the requirement or its
  acceptance criteria.
- Do NOT invent additional business flows, even if they are common behavior
  for this kind of feature.
- Do NOT introduce product-detail, remove-item, unauthorized-access,
  checkout, session-expiry, or any other scenario unless it is explicitly
  mentioned in the supplied requirement or acceptance criteria.
- Generate negative or edge scenarios only when they are directly implied by
  an explicit acceptance criterion. Do not add them merely for test coverage.
- Prefer fewer precise scenarios over broad or speculative coverage. Combine
  sequential acceptance criteria from one user flow into one end-to-end
  scenario instead of splitting them into loosely related scenarios.
- Each test scenario must be independently executable.
- Keep test steps clear enough that another AI agent can
  later convert them into Playwright automation.
- Before returning a scenario, remove it if any of its behavior cannot be
  justified by exact wording in the supplied requirement.

Software Requirement:

{user_story}
"""

        response = call_gemini_with_retry(
            lambda: self.client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": RequirementAnalysis,
                },
            )
        )

        if not response.text:
            raise RuntimeError(
                "Gemini returned an empty response."
            )

        return RequirementAnalysis.model_validate_json(
            response.text
        )
