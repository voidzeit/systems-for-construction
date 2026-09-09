# IFC panel clearance

This fixture exercises the dependency-free STEP reader. It imports two
electrical distribution boards and their `WorkingClearance` properties into a
provider-neutral Project World.

```bash
python -m sfc ifc-import examples/ifc-panel-clearance/demo.ifc --output .sfc/ifc-world.json
python -m sfc verify examples/ifc-panel-clearance/requirement.json .sfc/ifc-world.json
```

The reader is conservative: unsupported IFC entities are ignored rather than
invented. For production IFC coverage, an adapter can replace the reader while
returning the same Project World contract.

