# CLI architecture

The current flat CLI remains the compatibility surface. The target information architecture groups commands only as the underlying domain contracts become stable:

~~~text
sfc project
sfc requirements
sfc evidence
sfc work
sfc capability
sfc determine
sfc qa
sfc coordinate
sfc generate
sfc production
sfc ai
sfc connectors
sfc plugins
sfc runs
sfc report
sfc readiness
sfc doctor
sfc config
sfc serve
~~~

Existing commands such as verify, inspect, ifc-import, pdf-import, investigate, report, readiness, gateway and serve should remain reproducible during migration. A grouping change is an interface migration, not cosmetic cleanup.
