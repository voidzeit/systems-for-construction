# Bounded agent investigations

An SFC agent receives a task and a provider-neutral tool catalog. The provider
may request a read operation; the runtime checks the manifest before invoking
the registered tool, records the observation, and returns it to the provider
for the next turn.

```text
task → provider → tool call → policy check → observation → provider → candidate finding
```

The runtime enforces the action and wall-clock limits in the manifest. Tool
errors become observations and do not become authority. The result is always a
candidate finding; publication and approval remain outside the agent runtime.
