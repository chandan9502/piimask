# piimask

[![CI](https://github.com/chandan9502/piimask/actions/workflows/ci.yml/badge.svg)](https://github.com/chandan9502/piimask/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Mask UK personal data before text goes to an LLM, then put it back in the reply.**

Support tickets, emails and case notes are full of phone numbers, NHS numbers and card numbers.
Sending them to a hosted LLM can break data-protection rules. piimask swaps each value for a
placeholder such as `<UK_PHONE_1>`, keeps a private mapping, and restores the real values in
the model's answer. It is pure Python with no dependencies.

```text
Before: My email is jane.doe@example.com and my mobile is 07700 900123.
Sent:   My email is <EMAIL_1> and my mobile is <UK_PHONE_1>.
Reply:  We will text <UK_PHONE_1> when the refund is done.
After:  We will text 07700 900123 when the refund is done.
```

## What it finds

| Kind | Example (test value) | Check used to avoid false alarms |
|---|---|---|
| `EMAIL` | jane.doe@example.com | pattern |
| `UK_PHONE` | 07700 900123, +44 20 7946 0958 | 11 digits, UK ranges 01/02/03/07/08 |
| `UK_POSTCODE` | G12 8QQ | pattern |
| `NI_NUMBER` | AB 12 34 56 C | HMRC prefix rules |
| `NHS_NUMBER` | 943 476 5919 | modulus-11 check digit |
| `CARD` | 4111 1111 1111 1111 | Luhn check digit |
| `IBAN` | GB82 WEST 1234 5698 7654 32 | ISO 13616 modulus-97 |

A number that looks right but fails its check (an NHS number with the wrong check digit, a card
number that fails Luhn) is left alone. The same value always gets the same placeholder, even in a
different format (`07700 900123` and `07700900123`), so the model can still tell people apart.

## Install

Requires Python 3.10+.

```bash
pip install "git+https://github.com/chandan9502/piimask"
```

## Command line

```bash
# Count personal data without printing it. Exit code 1 if any is found (for CI or pre-commit).
piimask scan examples/support_ticket.txt
# {"found": 5, "counts": {"EMAIL": 1, "UK_PHONE": 1, "NHS_NUMBER": 1, "UK_POSTCODE": 1, "CARD": 1}}

# Mask, keeping the mapping in a file (it contains the real values: keep it private)
piimask mask examples/support_ticket.txt --mapping-out mapping.json > masked.txt

# ...send masked.txt to your LLM, save its answer as reply.txt...

piimask restore reply.txt --mapping mapping.json
```

All commands read stdin when no file is given. `--kinds email,uk_phone` limits what is looked
for. `piimask mask --json` prints the masked text, mapping and counts together.

## Python

```python
from piimask import mask, restore

result = mask("Email jane.doe@example.com about the refund.")
result.text      # 'Email <EMAIL_1> about the refund.'
result.mapping   # {'<EMAIL_1>': 'jane.doe@example.com'}

reply = "Sent the confirmation to <EMAIL_1>."   # what the LLM wrote
restore(reply, result.mapping)                 # 'Sent the confirmation to jane.doe@example.com.'
```

## Limitations

- **Names and street addresses are not detected.** They need a language model (named-entity
  recognition), which piimask deliberately avoids. Use it alongside one if you need that.
- Pattern-based: unusual formats (an NHS number split across lines, a phone number written in
  words) are missed. Postcodes and emails are matched by pattern only, with no check digit.
- UK-focused. Phone and ID checks follow UK rules; emails, cards and IBANs work for any country.
- The mapping file holds the original values. Treat it like the data itself.
- Masking reduces what you send; it does not by itself make a use of personal data lawful.

## Development

```bash
pip install -e ".[dev]"
ruff check .
python -m pytest
```

## Licence

MIT
