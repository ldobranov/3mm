# Optional AI clients

Shared provider clients extracted from the former in-Core Builder/Automations.
This package depends on requests and the Python standard library. It has no Core,
database, SDK, identity, billing or device authority dependency. Applications
choose whether to depend on it; it is excluded from the Core release payload.

Install explicitly with `pip install ./libraries/ai_clients`. Import clients
from `application_ai.groq_client`, `application_ai.openrouter_client`,
`application_ai.free_provider_client` or `application_ai.gateway`.
The independent distribution is `application-ai`; its name does not select a
provider or install anything into Core.

Run the independent tests from this directory with `python -m pytest -q`.
Tests use local stubs, without provider requests or credentials. Existing client
behavior and defaults are preserved; this extraction makes no new provider/model
availability claim. Applications must separately define connector/secret grants
and their retry/effect policy when porting these clients into a supported host.
