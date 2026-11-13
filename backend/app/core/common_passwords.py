"""Small deny-list of the most common passwords (FR-001). Length >= 10 already filters most; this blocks the rest."""

COMMON_PASSWORDS = frozenset(
    p.lower()
    for p in """
password1234 1234567890 0123456789 qwertyuiop qwerty12345 qwerty123456 1q2w3e4r5t 1qaz2wsx3edc
password123 password12345 password123456 passw0rd123 p@ssword123 p@ssw0rd123 letmein1234 letmein12345
iloveyou123 iloveyou1234 welcome1234 welcome12345 admin12345 admin123456 administrator monkey12345
dragon12345 football123 baseball123 abcdefghij abcd123456 abc1234567 1111111111 0000000000 9876543210
changeme123 trustno1234 sunshine123 princess123 superman123 whatever123 starwars123 123456789a a123456789
""".split()
)
