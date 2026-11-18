You write realistic questions that people in a survival situation would type into an offline phone assistant.

You are given one SEED passage from a survival manual. Write exactly {n_answerable} questions that the SEED passage fully answers, plus exactly {n_unanswerable} question(s) that sound related but that the SEED passage does NOT answer.

Vary the voice across questions:
- panicked and short, typed fast, maybe a typo ("cut my hand bad cant stop bleding")
- calm and specific ("how long should I boil stream water before drinking it")
- describing a situation instead of asking directly ("its getting dark and I have wet wood only")

Rules:
- Each question must stand alone. Never mention "the passage", "the manual" or "the text".
- Answerable questions must be fully answered by the SEED passage alone.
- Unanswerable questions must stay in the survival domain and must not be answerable from the SEED passage.
- Assign each question one category from: {categories}.

Return JSON only:
{{"questions": [{{"q": "...", "category": "...", "answerable": true}}]}}

SEED ({source_label}):
{seed_text}
