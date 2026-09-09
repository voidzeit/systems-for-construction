# Providers

LLM and vision integrations belong here and implement provider-neutral
interfaces. A provider may investigate and propose candidate evidence; it may
not publish a determination or approve a work package. The core remains usable
with no provider installed. `sfc.http_providers` includes small HTTP adapters
for OpenAI-compatible endpoints and Anthropic without making either vendor a
core dependency.
