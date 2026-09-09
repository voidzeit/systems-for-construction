# ADR 0003: Absence of evidence is not evidence of absence

Status: accepted

If an element lacks an observed property, SFC records an unknown subject and
reduces coverage. It does not invent zero and does not classify the subject as a
counterexample. This preserves the distinction between `NOT_MET` and
`INCOMPLETE`.

