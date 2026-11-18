import pytest

from piimask import KINDS, find_pii, mask, restore
from piimask.core import iban_valid, luhn_valid, nhs_number_valid, ni_number_valid, uk_phone_valid

# Test values only: Ofcom drama numbers, the NHS and card industry test numbers,
# the ISO example IBAN and example.com addresses.
TEXT = (
    "Patient Jane, email jane.doe@example.com, mobile 07700 900123, office +44 20 7946 0958. "
    "NHS number 943 476 5919, NI number AB 12 34 56 C, postcode G12 8QQ. "
    "Refund to card 4111 1111 1111 1111 or IBAN GB82 WEST 1234 5698 7654 32."
)


def kinds_found(text):
    return [m.kind for m in find_pii(text)]


def test_finds_every_kind_once():
    assert sorted(kinds_found(TEXT)) == sorted(
        ["EMAIL", "UK_PHONE", "UK_PHONE", "NHS_NUMBER", "NI_NUMBER", "UK_POSTCODE", "CARD", "IBAN"]
    )
    assert set(KINDS) == {"EMAIL", "IBAN", "CARD", "NHS_NUMBER", "NI_NUMBER", "UK_PHONE", "UK_POSTCODE"}


@pytest.mark.parametrize(
    "text",
    [
        "NHS number 943 476 5918",  # wrong check digit
        "card 4111 1111 1111 1112",  # fails Luhn
        "IBAN GB82 WEST 1234 5698 7654 33",  # fails mod 97
        "NI QQ 12 34 56 C",  # Q is never used as a first letter
        "NI GB 12 34 56 A",  # GB is a banned prefix
        "call 0770 090",  # too short for a UK number
        "order 12345 shipped",
    ],
)
def test_invalid_lookalikes_are_ignored(text):
    assert kinds_found(text) == []


def test_checks():
    assert luhn_valid("4111-1111-1111-1111")
    assert nhs_number_valid("9434765919") and not nhs_number_valid("9434765910")
    assert iban_valid("gb82 west 1234 5698 7654 32")
    assert ni_number_valid("AB123456C") and not ni_number_valid("DA123456C")
    assert uk_phone_valid("+44 (0)20 7946 0958") and uk_phone_valid("07700900123")
    assert not uk_phone_valid("05700900123")  # 05 is not a UK number range we accept


def test_mask_replaces_with_numbered_placeholders():
    result = mask(TEXT)
    originals = ("jane.doe@example.com", "07700 900123", "943 476 5919", "G12 8QQ", "4111 1111 1111 1111")
    for original in originals:
        assert original not in result.text
    assert "<EMAIL_1>" in result.text and "<UK_PHONE_2>" in result.text
    assert result.counts()["UK_PHONE"] == 2
    assert "Patient Jane" in result.text  # names are not detected (documented limitation)


def test_same_value_gets_same_placeholder_across_formats():
    result = mask("Call 07700 900123. Again: 07700900123. Or 07700 900456.")
    assert result.text == "Call <UK_PHONE_1>. Again: <UK_PHONE_1>. Or <UK_PHONE_2>."
    assert result.mapping == {"<UK_PHONE_1>": "07700 900123", "<UK_PHONE_2>": "07700 900456"}


def test_restore_round_trip():
    result = mask(TEXT)
    assert restore(result.text, result.mapping) == TEXT


def test_restore_in_an_llm_reply():
    result = mask("Email jane.doe@example.com about the refund.")
    reply = "Draft: Dear customer, we have sent the refund confirmation to <EMAIL_1>."
    assert restore(reply, result.mapping).endswith("to jane.doe@example.com.")
    assert restore("<EMAIL_9> stays", result.mapping) == "<EMAIL_9> stays"


def test_kinds_filter():
    result = mask(TEXT, kinds=["email"])
    assert list(result.counts()) == ["EMAIL"]
    with pytest.raises(ValueError):
        mask(TEXT, kinds=["passport"])


def test_text_without_pii_is_unchanged():
    result = mask("The meeting is on Tuesday at 10am.")
    assert result.text == "The meeting is on Tuesday at 10am."
    assert result.mapping == {} and result.matches == []
