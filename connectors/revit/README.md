# Revit connector

Revit integration remains an adapter. It may extract native parameters, relationships, schedules, geometry and identity into Project World, and may execute explicitly authorized model actions through transactions.

SFC domain code must not import the Autodesk API.

The adjacent plugin manifest defines the **public connector contract only**. A deployable Revit add-in is not claimed by this directory until an implementation and release evidence are added.

Canonical surface role:

\[
Revit = PointOfWork
\]

Side-effecting actions remain governed by capability, project policy, user authority, validation and evidence.
