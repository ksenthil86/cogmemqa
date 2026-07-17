/** Demo scenarios from schema/cogmem_ontology.yaml `demo_scenarios`. */

export const DEMO_SCENARIOS: { label: string; question: string }[] = [
  {
    label: "Test coverage",
    question: "What is the current test coverage?",
  },
  {
    label: "Provenance chain",
    question: "Show me the provenance chain for the account opening requirement.",
  },
  {
    label: "Last commit impact",
    question:
      "Which files were touched by the last commit and what requirements are affected?",
  },
  {
    label: "Security findings",
    question: "Are there any open security findings on high-priority requirements?",
  },
];
