"""Verbatim port of PropRAG (EMNLP 2025) proposition_extraction prompt.

Source: PropRAG/src/proprag/prompts/templates/proposition_extraction.py
PropRAG repo: https://github.com/ReLink-Inc/PropRAG

This file ports the SYSTEM prompt and USER frame VERBATIM. The only differences:
  - Removed `from ...utils.llm_utils import convert_format_to_template`
  - Replaced PromptTemplateManager.render() machinery with plain str.format()
  - Exposed PROPOSITION_SYSTEM and PROPOSITION_USER_FRAME for direct use
  - Added build_messages() helper returning chat-message-list for our LLM wrappers

Method v2.0.2 §B.2.2.1 — Q1=c locked: W1 uses PropRAG proposition extraction.
Method v2.0.2 §B.2.2 — Q3=ii locked: feed HippoRAG-v2 triple-derived entities.
"""

PROPOSITION_SYSTEM = """Your task is to analyze text passages and break them down into precise, atomic propositions using a specified list of named entities. A proposition is a fully contextualized statement that expresses a single unit of meaning with complete specificity about the relationships described.

For each proposition:
1. Extract a complete, standalone statement that preserves the full context
2. Use ONLY the entities provided in the named_entities list - do not introduce new entities
3. Ensure each proposition contains only ONE claim or relationship
4. Be extremely specific about which entities are involved in each relationship
5. Maintain clear causal connections between related statements

Respond with a JSON object containing a list of propositions, where each proposition is an object with:
- "text": The full proposition text as a complete, contextualized statement
- "entities": An array of entities from the named_entities list that appear in that proposition

Critical Guidelines:
- ONLY use entities from the provided named_entities list
- Make relationships explicit and specific - clarify exactly which entities relate to which other entities
- Clarify precisely which entity a modifier applies to (e.g., specify which product had "80% improvement")
- Establish clear connections between related facts (e.g., "Adobe optimized their applications FOR THE M1 CHIP")
- Connect comparative statements to their specific reference points (e.g., "Adobe's applications on the M1 chip improved by 80% compared to Intel-based Macs")
- Preserve temporal information and causal relationships between events
- Make each proposition stand alone with all necessary context
- Include ALL relevant entities from the named_entities list in both the proposition text and entities array
- Ensure the collection of propositions captures ALL meaningful information in the passage

Example 1:
Passage: In 2020, after Apple launched the M1 chip, major software companies like Adobe optimized their applications, improving performance by up to 80% compared to Intel-based Macs.

Named entities: ["Apple", "M1 chip", "2020", "Adobe", "Adobe's applications", "Intel-based Macs", "80% performance improvement"]

{
  "propositions": [
    {
      "text": "Apple launched the M1 chip in 2020.",
      "entities": ["Apple", "M1 chip", "2020"]
    },
    {
      "text": "Adobe optimized their applications specifically for the M1 chip after its launch.",
      "entities": ["Adobe", "Adobe's applications", "M1 chip"]
    },
    {
      "text": "Adobe's applications running on the M1 chip improved performance by up to 80% compared to the same applications running on Intel-based Macs.",
      "entities": ["Adobe", "Adobe's applications", "M1 chip", "80% performance improvement", "Intel-based Macs"]
    }
  ]
}


Example 2:
Passage: In September 2023, Apple replaced the Lightning connector with USB-C on the iPhone 15, after the European Union passed regulations requiring all mobile devices to use a standardized charging port.

Named entities: ["Apple", "Lightning connector", "USB-C connector", "iPhone 15", "European Union", "regulations", "standardized charging port", "mobile devices", "September 2023"]

{
  "propositions": [
    {
      "text": "The iPhone 15 uses a USB-C connector instead of the Lightning connector.",
      "entities": ["iPhone 15", "USB-C connector", "Lightning connector"]
    },
    {
      "text": "The European Union passed regulations requiring all mobile devices to use a standardized charging port.",
      "entities": ["European Union", "regulations", "mobile devices", "standardized charging port"]
    },
    {
      "text": "Apple changed from Lightning to USB-C on the iPhone 15 due to the European Union regulations in September 2023.",
      "entities": ["Apple", "Lightning connector", "USB-C connector", "iPhone 15", "European Union", "regulations", "September 2023"]
    }
  ]
}"""


# Verbatim from PropRAG `proposition_frame`
PROPOSITION_USER_FRAME = """
Passage:
```
{passage}
```

Named entities: {named_entities}"""


def build_messages(passage: str, named_entities_json: str) -> list:
    """Build chat-message-list for LLM, matching PropRAG's prompt_template structure.

    Args:
        passage: chunk text
        named_entities_json: JSON-encoded list of entity strings (use json.dumps)

    Returns:
        List of {role, content} dicts ready for CacheGemini.infer() or compatible.
    """
    return [
        {"role": "system", "content": PROPOSITION_SYSTEM},
        {"role": "user", "content": PROPOSITION_USER_FRAME.format(
            passage=passage,
            named_entities=named_entities_json,
        )},
    ]
