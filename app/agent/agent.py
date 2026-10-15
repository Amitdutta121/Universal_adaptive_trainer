"""The professor agent: one Pydantic AI agent, its model from the ``agent`` role's settings.

The model is chosen per request (:func:`agent_model`), so a change on the Settings screen
applies to the next message without a restart. The instructions describe the job and the
tools; what is allowed is decided by the tools' own service calls, never by this prompt.
"""

from __future__ import annotations

from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import Settings
from app.llm.availability import require_llm
from app.llm.client import OPENROUTER_BASE_URL
from app.settings_store import ModelRole, settings_for

from .tools import AgentDeps, toolset

INSTRUCTIONS = """\
You help a professor set up and run a course in the Adaptive Trainer Studio.
The usual order is: import material, propose and approve a curriculum, choose question
styles, plan and run generation, review, then publish a question set to students.

Use the tools to read and change the course; never invent ids, counts or results.
When a tool returns an `error`, tell the professor what it says and what they can do.
Some actions wait for the professor to approve them in the chat; say what you are asking
for and why, and do not repeat a request they rejected unless they ask.
Keep replies short."""


def agent_model(settings: Settings | None = None) -> Model:
    """The chat model the ``agent`` role is set to, over its OpenAI-compatible endpoint.

    Raises:
        ConfigurationError: no provider or API key is configured for the role.
    """
    settings = require_llm(settings_for(ModelRole.AGENT, settings))
    assert settings.llm_api_key is not None  # require_llm checked it
    provider = OpenAIProvider(
        base_url=settings.llm_base_url or OPENROUTER_BASE_URL,
        api_key=settings.llm_api_key.get_secret_value(),
    )
    return OpenAIChatModel(settings.llm_model, provider=provider)


#: ``DeferredToolRequests``: a run that reaches an approval-required call ends there, and the
#: AG-UI adapter turns it into an interrupt for the chat panel's approval card.
professor_agent: Agent[AgentDeps, str | DeferredToolRequests] = Agent(
    deps_type=AgentDeps,
    output_type=[str, DeferredToolRequests],
    instructions=INSTRUCTIONS,
    toolsets=[toolset],
    name="professor",
)
