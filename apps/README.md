# Applications

Studio, API and worker applications consume SFC contracts. They should keep
workflow and persistence concerns outside the domain package.

The local reference API is available with `sfc serve`. It exposes `/health`,
`/project`, `/elements` and `/run` as read-only JSON endpoints. A web Studio
can be layered over these endpoints without moving domain logic into the UI.
