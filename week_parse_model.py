#!/usr/bin/env python3
"""Faithful model of 小应校园's week-text parser, reconstructed from libapp.so disassembly.

parseWeekText2RangedNumbers  (xiaoying_timetable_common/utils.dart)
  0x16a8350  split(",")
  0x16a8400  if part.contains("周(单)") : substring(0, len-4) -> rangeFromString, type=ODD
  0x16a8550  elif part.contains("周(双)") : substring(0, len-4) -> rangeFromString, type=EVEN
  0x16a86a0  elif part.contains("周")     : substring(0, len-1) -> rangeFromString, type=ALL
             else                          :                      rangeFromString, type=ALL
rangeFromString  (0xb43940)
  if s.contains("-") : int.parse(left), int.parse(right)
  else              : int.parse(s)
mapChinesePunctuations (0x16a88a4, patched in v0.5)
  maps 【】；（） ; and DROPS '第' (U+7B2C) after the v0.5 patch
"""

class ParseError(Exception):
    pass


def map_chinese_punctuations(s):
    table = {0x3010: '[', 0x3011: ']', 0xFF06: '&', 0xFF08: '(', 0xFF09: ')'}
    out = []
    for ch in s:
        cp = ord(ch)
        if cp == 0x7B2C:      # '第' -> dropped by the v0.5 patch
            continue
        out.append(table.get(cp, ch))
    return ''.join(out)


def dart_int_parse(s):
    if not s:
        raise ParseError(f'FormatException: empty string')
    body = s
    if body[0] in '+-':
        body = body[1:]
    if not body or not body.isdigit():
        raise ParseError(f'FormatException: Invalid radix-10 number -> {s!r}')
    return int(s)


def range_from_string(s):
    if '-' in s:
        left, right = s.split('-', 1)
        return (dart_int_parse(left), dart_int_parse(right))
    v = dart_int_parse(s)
    return (v, v)


def parse_week_text(text):
    out = []
    for part in map_chinese_punctuations(text).split(','):
        if '周(单)' in part:
            body, kind = part[:len(part) - 4], 'ODD'
        elif '周(双)' in part:
            body, kind = part[:len(part) - 4], 'EVEN'
        elif '周' in part:
            body, kind = part[:len(part) - 1], 'ALL'
        else:
            body, kind = part, 'ALL'
        out.append((range_from_string(body), kind))
    return out


CASES = [
    ('第18周',      [(18, 18), 'ALL']),
    ('1-18周',      [(1, 18), 'ALL']),
    ('第1-18周',    [(1, 18), 'ALL']),
    ('1,3,5周',     'multi'),
    ('18周(单)',    [(18, 18), 'ODD']),
    ('1-18周(双)',  [(1, 18), 'EVEN']),
    ('第18',        [(18, 18), 'ALL']),      # 真实崩溃输入
    ('第1-18',      [(1, 18), 'ALL']),
    ('1-18周(单)',  [(1, 18), 'ODD']),
    ('第1-18周(单)', [(1, 18), 'ODD']),
]

print(f"{'input':<16} {'result':<44} verdict")
print('-' * 78)
for text, expect in CASES:
    try:
        got = parse_week_text(text)
        verdict = 'OK'
        if expect == 'multi':
            if len(got) != 3 or [g[0] for g in got] != [(1, 1), (3, 3), (5, 5)]:
                verdict = 'MISMATCH'
        elif [got[0][0], got[0][1]] != expect:
            verdict = 'MISMATCH'
        print(f"{text:<16} {str(got):<44} {verdict}")
    except ParseError as e:
        print(f"{text:<16} {'-':<44} FAIL: {e}")
