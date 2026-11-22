import inspect

from app.clients.llm import LLMClient
from app.extraction.llm import DraftingLlm, StructuredLlm


def test_real_client_satisfies_the_extraction_protocols():
    client = LLMClient(client=object())  # no network, no key
    assert isinstance(client, StructuredLlm)
    assert isinstance(client, DraftingLlm)
    params = list(inspect.signature(LLMClient.extract_structured).parameters)
    assert params[:4] == ["self", "system", "user", "schema"]
    assert list(inspect.signature(LLMClient.draft_text).parameters)[:3] == [
        "self",
        "system",
        "user",
    ]
