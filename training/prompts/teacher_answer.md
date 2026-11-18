You are producing the ideal reply for a small offline model to imitate. The small model will see the SYSTEM RULES and USER MESSAGE below and must learn to reply exactly as you do.

Follow the SYSTEM RULES with zero deviation. Use only facts stated in the numbered sources. If the sources do not fully answer the question, use the NOT IN LIBRARY format. When unsure, prefer NOT IN LIBRARY over a partial answer.

Also tag the item for human review:
- "medical" if the reply gives any first aid, medication, or injury treatment step
- "plant" if the reply concerns eating, identifying, or using plants, fungi, or animals as food or medicine
- "water" if the reply concerns making water safe to drink

Return JSON only:
{{"answer": "<the exact reply text>", "refusal": <true|false>, "used_sources": [<source numbers>], "review_flags": [<zero or more of "medical","plant","water">]}}

SYSTEM RULES:
{system_rules}

USER MESSAGE:
{user_message}
