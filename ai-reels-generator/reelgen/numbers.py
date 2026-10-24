"""Numbers written out in English words before an English voice reads them.

The Microsoft 'Multilingual' voices (Andrew, the default) pick the language from the text, and in an English script
about India (lakh, crore, rupees) they read the digits in Hindi: the user heard "ek lakh" for "1 lakh", and "every
number spoken in Hinglish but the script is English". Words leave them nothing to guess: "1 lakh" -> "one lakh",
"₹2.5 crore" -> "two point five crore rupees", "1,400" -> "one thousand four hundred", "2024" -> "twenty twenty-four",
"18%" -> "eighteen percent", "3rd" -> "third", "1990s" -> "nineteen nineties", "10-15" -> "ten to fifteen",
"2022-23" -> "twenty twenty-two to twenty-three", "7:30" -> "seven thirty".

Only for English narration (voice.py `_synthesize`, never a Hindi or Sarvam voice or mixed Hinglish, where the Hindi
reading is wanted). Indian grouping ("1,00,000") is read in lakh and crore; Western grouping in thousands and millions.
Digits glued to letters (5G, G20, 80C) and long digit runs (phone numbers) are left as written; COVID-19 is read
"COVID-nineteen".
"""

from __future__ import annotations

import re

try:
    from num2words import num2words
except ImportError:  # not installed yet (an app updated without its packages): numbers stay as written
    num2words = None

UNITS = r"lakh|lakhs|crore|crores|thousand|million|billion|trillion|hundred"
CURRENCY = {"₹": "rupees", "rs": "rupees", "rs.": "rupees", "inr": "rupees", "$": "dollars", "usd": "dollars",
            "€": "euros", "£": "pounds"}
NUM = r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?"
# Not inside a word (5G, G20, COVID-19 stay as written): no letter or digit right before or after.
_TIME = re.compile(r"(?<![\w:.])(\d{1,2}):(\d{2})(?![\w:])")
_TOKEN = re.compile(
    rf"(?<![\w.:])(?P<cur>₹|\$|€|£|(?:Rs\.?|INR|USD)\s?)?(?P<num>{NUM})"
    rf"(?:(?P<range>\s?[-–]\s?)(?P<num2>{NUM}))?"
    rf"(?P<suffix>%|st|nd|rd|th|s(?=\b))?"
    rf"(?:\s?(?P<unit>{UNITS})\b)?(?![\w:])", re.I)


def _words(n: str, indian: bool = False) -> str:
    whole, _, frac = n.replace(",", "").partition(".")
    text = num2words(int(whole), lang="en_IN" if indian else "en").replace(",", "")
    if frac:  # 2.05 -> two point zero five (every digit, as said)
        text += " point " + " ".join(num2words(int(d)) for d in frac)
    return text


def _indian(n: str) -> bool:
    """1,00,000 is written the Indian way (lakh, crore); 100,000 the Western way."""
    return bool(re.fullmatch(r"\d{1,2}(,\d{2})+,\d{3}(\.\d+)?", n))


def _year(n: str) -> bool:
    return "," not in n and "." not in n and len(n) == 4 and 1100 <= int(n) <= 2099


def _say(m: re.Match) -> str:
    raw, num, num2, suffix = m.group(0), m.group("num"), m.group("num2"), (m.group("suffix") or "")
    cur = (m.group("cur") or "").strip().lower()
    unit = (m.group("unit") or "").lower()
    digits = num.replace(",", "").split(".")[0]
    if len(digits) > 12 or (len(digits) > 9 and "," not in num and not cur):  # a phone number, an ID: as written
        return raw
    if suffix.lower() in ("st", "nd", "rd", "th") and "." not in num and not num2:
        return num2words(int(digits), to="ordinal", lang="en")
    plural = suffix.lower() == "s" and not num2
    if plural and _year(num):  # the 1990s
        spoken = num2words(int(num), to="year", lang="en")
        return (spoken[:-1] + "ies" if spoken.endswith("y") else spoken + "s") + (f" {unit}" if unit else "")
    if plural and "." not in num and "," not in num and int(digits) % 10 == 0 and 10 <= int(digits) <= 90:
        tens = num2words(int(digits))  # the 20s -> the twenties
        return tens[:-1] + "ies" if tens.endswith("y") else tens + "s"
    if suffix.lower() == "s" and not plural:
        return raw
    year = not cur and not unit and suffix != "%" and _year(num) and (not num2 or _year(num2) or len(num2) == 2)
    say = (lambda x: num2words(int(x), to="year", lang="en") if len(x) == 4 else _words(x)) if year \
        else (lambda x: _words(x, _indian(x)))
    spoken = say(num) + (f" to {say(num2)}" if num2 else "")
    if suffix == "%":
        spoken += " percent"
    if unit:
        spoken += f" {unit}"
    if cur:
        spoken += f" {CURRENCY.get(cur, '')}".rstrip()
    if plural:  # '20s' after a number that isn't a year: as written
        return raw
    return spoken


def speakable(text: str) -> str:
    """`text` with its numbers in English words (see the module's notes); everything else unchanged."""
    if num2words is None or not re.search(r"\d", text):
        return text
    text = _TIME.sub(lambda m: num2words(int(m.group(1))) + (
        "" if m.group(2) == "00" else " oh " + num2words(int(m.group(2))) if m.group(2).startswith("0")
        else " " + num2words(int(m.group(2)))), text)
    return _TOKEN.sub(_say, text)


# ---------- Hindi number words, for the Sarvam voices ----------
# Sarvam read "₹5,000" as "rupees five zero zero zero" in the user's video (its docs say v3/v4 normalise numbers,
# and that commas help; it didn't). num2words has no Hindi, so the words are written here: 0-99 each have their own
# word in Hindi, then सौ / हज़ार / लाख / करोड़ in the Indian grouping.
HI_0_99 = (
    "शून्य एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस "
    "बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस छत्तीस "
    "सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास पचास "
    "इक्यावन बावन तिरेपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ इकसठ बासठ तिरेसठ चौंसठ पैंसठ छियासठ सड़सठ "
    "अड़सठ उनहत्तर सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उन्यासी अस्सी इक्यासी बयासी "
    "तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी नब्बे इक्यानवे बानवे तिरानवे चौरानवे पचानवे छियानवे सत्तानवे "
    "अट्ठानवे निन्यानवे").split()
assert len(HI_0_99) == 100
HI_CURRENCY = {"₹": "रुपये", "rs": "रुपये", "rs.": "रुपये", "inr": "रुपये", "$": "डॉलर", "usd": "डॉलर", "€": "यूरो", "£": "पाउंड"}


def hindi_words(n: int) -> str:
    """5000 -> पाँच हज़ार, 1,25,000 -> एक लाख पच्चीस हज़ार, 3,20,00,000 -> तीन करोड़ बीस लाख."""
    if n < 100:
        return HI_0_99[n]
    parts = []
    for size, name in ((10 ** 7, "करोड़"), (10 ** 5, "लाख"), (1000, "हज़ार"), (100, "सौ")):
        count, n = divmod(n, size)
        if count:
            parts.append(f"{hindi_words(count)} {name}")
    if n:
        parts.append(HI_0_99[n])
    return " ".join(parts)


def _hi_number(n: str, year: bool = False) -> str:
    whole, _, frac = n.replace(",", "").partition(".")
    value = int(whole)
    if year and 1100 <= value <= 1999 and value % 100:  # 1990 -> उन्नीस सौ नब्बे, as years are said
        text = f"{HI_0_99[value // 100]} सौ {HI_0_99[value % 100]}"
    else:
        text = hindi_words(value)
    if frac:  # 2.5 -> दो दशमलव पाँच (every digit, as said)
        text += " दशमलव " + " ".join(HI_0_99[int(d)] for d in frac)
    return text


def _say_hi(m: re.Match) -> str:
    raw, num, num2, suffix = m.group(0), m.group("num"), m.group("num2"), (m.group("suffix") or "")
    cur = (m.group("cur") or "").strip().lower()
    unit = m.group("unit") or ""
    digits = num.replace(",", "").split(".")[0]
    if len(digits) > 12 or (len(digits) > 9 and "," not in num and not cur):  # a phone number, an ID: as written
        return raw
    if suffix.lower() in ("st", "nd", "rd", "th") and "." not in num and not num2:
        return num2words(int(digits), to="ordinal", lang="en") if num2words else raw
    if suffix.lower() == "s":  # the 1990s and the like: the number, as said
        suffix = ""
    year = not cur and not unit and suffix != "%" and _year(num)
    spoken = _hi_number(num, year) + (f" से {_hi_number(num2, year)}" if num2 else "")
    if suffix == "%":
        spoken += " प्रतिशत"
    if unit:
        spoken += f" {unit}"
    if cur:
        spoken += f" {HI_CURRENCY.get(cur, '')}".rstrip()
    return spoken


def speakable_hindi(text: str) -> str:
    """`text` with its numbers in Hindi words (Devanagari); everything else unchanged."""
    if not re.search(r"\d", text):
        return text
    text = _TIME.sub(lambda m: hindi_words(int(m.group(1))) + ("" if m.group(2) == "00" else " " + hindi_words(int(m.group(2)))), text)
    return _TOKEN.sub(_say_hi, text)


def speakable_for(text: str) -> str:
    """Numbers in the line's own language: Hindi words in a line with Devanagari, else English words."""
    return speakable_hindi(text) if re.search("[ऀ-ॿ]", text) else speakable(text)
