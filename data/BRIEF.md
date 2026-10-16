# Selection rules for new records

You choose from machine-extracted messages; you never write text of your own except `context`.
Input: `data/extracted/*.json` files listed in the job prompt (raw candidate messages with `source` url, title and locator).
Output: one JSON array in the part file named in the job prompt. Nothing else is changed.
A separate script checks every excerpt and chat message against the source text word for word; a single altered word fails the job.

## Email record
```json
{
  "id": "short-unique-slug",
  "kind": "email",
  "from": "Mark Zuckerberg", "to": ["David Ebersman"], "cc": [],
  "date": "2012-02-27", "subject": "Re: ...",
  "excerpt": "verbatim text from the email, 1 to 6 sentences, at most 600 characters, cut only at sentence ends",
  "context": "one neutral sentence of your own, at most 160 characters",
  "company": ["Meta"], "people": ["Mark Zuckerberg", "David Ebersman"],
  "source": {"title": "copied from the candidate", "url": "copied from the candidate", "locator": "copied from the candidate"}
}
```

## Chat record
```json
{
  "id": "short-unique-slug",
  "kind": "chat",
  "date": "2014-03-01",
  "messages": [{"speaker": "Name", "text": "verbatim, at most 600 characters"}],
  "context": "...", "company": ["..."], "people": ["..."],
  "source": {"title": "...", "url": "...", "locator": "..."}
}
```
At most 30 messages, in source order, no gaps in the middle of an exchange you quote.

## Rules (both kinds)
- `source.url`, `title`, `locator` are copied unchanged from the extracted candidate. `date` as precise as the source gives (YYYY-MM-DD, YYYY-MM or YYYY).
- Excerpt and message text are VERBATIM from the extracted text. Fix nothing except line breaks. If a passage is unreliable (OCR noise), skip it. Never invent, merge or reconstruct text. Keep original spelling.
- Business messages of executives and public figures only. Drop private people's personal details (home addresses, phone numbers, family matters, health).
- Pick the interesting ones: decisions, strategy, famous lines, candid moments. Skip scheduling, boilerplate and anything already in `data/emails.json` (same sender, date and start of text).
- No em-dashes in your own text (`context`); keep any that are in the original.
- Nothing worth keeping: write `[]`.
