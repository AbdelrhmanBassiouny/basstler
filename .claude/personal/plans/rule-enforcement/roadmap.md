# rule-enforcement - standing rules

- A rule's checkable part is a condition over a typed Action. A part only a person can judge stays guidance, as a rule of its own.
- The guard answers allow, ask or block. Every ask and block names the rule id, why it applies and what to run instead.
- An action the guard cannot parse, or a guard that cannot load, leads to ask, never to allow.
- A personal layer may tighten any rule. Loosening a shipped or repository rule needs an explicit override with a reason, shown wherever the rule is.
- A rule changes by refinement, an exception under the rule it corrects, never by an edit in place. Logged decisions are the cases every change is replayed against.
- The rule engine is an interface. Declared conditions are the first engine and krrood's EQL-RDR the second, added as a dependency once krrood's light core is released.
- The RDR's expert may be the user or the session's LLM. An LLM's proposal takes effect only after the user confirms it.
- A skill-scoped rule is a rule whose scope is that skill, not a document a session must remember to read.
