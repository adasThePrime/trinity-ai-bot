from __future__ import annotations

import re
from dataclasses import dataclass

from aiogram.types import MessageEntity


@dataclass
class _Span:
    start: int
    end: int = 0
    entity_type: str = ""
    url: str | None = None
    language: str | None = None


_MARKER_ENTITY = {
    "**": "bold",
    "__": "bold",
    "*": "italic",
    "_": "italic",
    "~~": "strikethrough",
    "||": "spoiler"
}

_RE_FENCED = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
_RE_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_RE_LINK = re.compile(r"\[([^\[\]]+?)\]\((https?://[^\s\)]+)\)")
_RE_HEADING = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
_RE_BLOCKQUOTE = re.compile(r"^>\s?(.*)$", re.MULTILINE)
_RE_BULLET = re.compile(r"^[ \t]*[*\-][ \t]+(?=\S)", re.MULTILINE)
_RE_HORIZONTAL_RULE = re.compile(r"^[ ]{0,3}(?:-[ ]*){3,}$", re.MULTILINE)

_RE_MENTION = re.compile(r"(?<!\w)@([A-Za-z][A-Za-z0-9_]{4,31})(?!\w)")
_RE_BOT_CMD = re.compile(r"(?<!\w)/([A-Za-z0-9_]{1,64})(?:@[A-Za-z0-9_]{1,64})?(?!\w)")
_RE_HASHTAG = re.compile(r"(?<!\w)#([A-Za-z]\w{0,63})(?!\w)")
_RE_URL = re.compile(r"(?<!\w)(https?://[^\s<>\")\]]+)")
_RE_EMAIL = re.compile(r"(?<!\w)([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})")
_RE_PHONE = re.compile(r"(?<!\w)(\+\d[\d\-\s]{6,18}\d)(?!\w)")

_INLINE_MARKERS = ["**", "__", "~~", "||", "*", "_"]

_PLACEHOLDER_PRE = "\x00PRE{}\x00"
_PLACEHOLDER_CODE = "\x00CODE{}\x00"
_PLACEHOLDER_LINK = "\x00LINK{}\x00"
_RE_PH_PRE = re.compile(r"\x00PRE(\d+)\x00")
_RE_PH_CODE = re.compile(r"\x00CODE(\d+)\x00")
_RE_PH_LINK = re.compile(r"\x00LINK(\d+)\x00")

_AUTO_PATTERNS = [
    (_RE_URL,     "url"),
    (_RE_EMAIL,   "email"),
    (_RE_MENTION, "mention"),
    (_RE_BOT_CMD, "bot_command"),
    (_RE_HASHTAG, "hashtag"),
    (_RE_PHONE,   "phone_number")
]


def _utf16_len(text: str) -> int:
    count = 0
    for ch in text:
        count += 2 if ord(ch) > 0xFFFF else 1
    return count


def _utf16_offset(text: str, char_index: int) -> int:
    return _utf16_len(text[:char_index])


def _extract_protected(
    text: str
) -> tuple[str, list[tuple[str, str]], list[str], list[tuple[str, str]]]:
    pre_blocks = []
    code_spans = []
    links = []

    def _sub_pre(m):
        idx = len(pre_blocks)
        pre_blocks.append((m.group(1), m.group(2)))
        return _PLACEHOLDER_PRE.format(idx)

    text = _RE_FENCED.sub(_sub_pre, text)

    def _sub_code(m):
        idx = len(code_spans)
        code_spans.append(m.group(1))
        return _PLACEHOLDER_CODE.format(idx)

    text = _RE_INLINE_CODE.sub(_sub_code, text)

    def _sub_link(m):
        idx = len(links)
        links.append((m.group(1), m.group(2)))
        return _PLACEHOLDER_LINK.format(idx)

    text = _RE_LINK.sub(_sub_link, text)
    return text, pre_blocks, code_spans, links


def _strip_horizontal_rules(text: str) -> str:
    return _RE_HORIZONTAL_RULE.sub("", text)


def _headings_to_bold(text: str) -> str:
    return _RE_HEADING.sub(r"**\1**", text)


def _bullets_to_dot(text: str) -> str:
    return _RE_BULLET.sub("• ", text)


def _is_formatting_marker(text: str, pos: int, marker: str) -> bool:
    if len(marker) > 1:
        return True

    end_pos = pos + len(marker)

    if marker == "_":
        before_is_word = pos > 0 and text[pos - 1].isalnum()
        after_is_word = end_pos < len(text) and text[end_pos].isalnum()
        if before_is_word and after_is_word:
            return False

    before_space = pos == 0 or text[pos - 1] in (" ", "\t", "\n")
    after_space = end_pos >= len(text) or text[end_pos] in (" ", "\t", "\n")

    if before_space and after_space:
        return False

    return True


def _parse_inline(text: str) -> tuple[str, list[_Span]]:
    result_chars = []
    spans = []
    open_stack = []

    i = 0
    plain_offset = 0

    while i < len(text):
        if text[i] == "\x00":
            end = text.index("\x00", i + 1) + 1
            chunk = text[i:end]
            result_chars.append(chunk)
            plain_offset += _utf16_len(chunk)
            i = end
            continue

        matched_marker = None
        for m in _INLINE_MARKERS:
            if text[i:i + len(m)] == m:
                if _is_formatting_marker(text, i, m):
                    matched_marker = m
                    break

        if matched_marker is None:
            ch = text[i]
            result_chars.append(ch)
            plain_offset += _utf16_len(ch)
            i += 1
            continue

        mlen = len(matched_marker)

        close_idx = None
        for si in range(len(open_stack) - 1, -1, -1):
            if open_stack[si][0] == matched_marker:
                close_idx = si
                break

        if close_idx is not None:
            open_marker, open_offset, _ = open_stack.pop(close_idx)
            entity_type = _MARKER_ENTITY.get(open_marker, "bold")
            spans.append(_Span(start=open_offset, end=plain_offset, entity_type=entity_type))
            i += mlen
        else:
            open_stack.append((matched_marker, plain_offset, len(result_chars)))
            i += mlen

    if open_stack:
        unmatched_positions = {offset for _, offset, _ in open_stack}
        result_chars2 = []
        spans2 = []
        open_stack2 = []
        i = 0
        plain_offset2 = 0

        while i < len(text):
            if text[i] == "\x00":
                end = text.index("\x00", i + 1) + 1
                chunk = text[i:end]
                result_chars2.append(chunk)
                plain_offset2 += _utf16_len(chunk)
                i = end
                continue

            matched_marker2 = None
            for m in _INLINE_MARKERS:
                if text[i:i + len(m)] == m:
                    if _is_formatting_marker(text, i, m):
                        matched_marker2 = m
                        break

            if matched_marker2 is None or plain_offset2 in unmatched_positions:
                if matched_marker2 and plain_offset2 in unmatched_positions:
                    result_chars2.append(matched_marker2)
                    plain_offset2 += _utf16_len(matched_marker2)
                    i += len(matched_marker2)
                else:
                    ch = text[i]
                    result_chars2.append(ch)
                    plain_offset2 += _utf16_len(ch)
                    i += 1
                continue

            mlen2 = len(matched_marker2)
            close_idx2 = None
            for si in range(len(open_stack2) - 1, -1, -1):
                if open_stack2[si][0] == matched_marker2:
                    close_idx2 = si
                    break

            if close_idx2 is not None:
                open_m2, open_off2, _ = open_stack2.pop(close_idx2)
                entity_type2 = _MARKER_ENTITY.get(open_m2, "bold")
                spans2.append(_Span(start=open_off2, end=plain_offset2, entity_type=entity_type2))
                i += mlen2
            else:
                open_stack2.append((matched_marker2, plain_offset2, len(result_chars2)))
                i += mlen2

        if open_stack2:
            return text, []

        return "".join(result_chars2), spans2

    return "".join(result_chars), spans


def _parse_blockquotes(text: str) -> tuple[str, list[tuple[int, int]]]:
    lines = text.split("\n")
    new_lines = []
    quote_ranges = []
    in_quote = False
    quote_start = 0

    for idx, line in enumerate(lines):
        m = _RE_BLOCKQUOTE.match(line)
        if m:
            new_lines.append(m.group(1))
            if not in_quote:
                in_quote = True
                quote_start = idx
        else:
            if in_quote:
                quote_ranges.append((quote_start, idx - 1))
                in_quote = False
            new_lines.append(line)

    if in_quote:
        quote_ranges.append((quote_start, len(lines) - 1))

    return "\n".join(new_lines), quote_ranges


def _auto_detect(text, existing_spans):
    new_spans = []
    occupied = set()
    for s in existing_spans:
        for p in range(s.start, s.end):
            occupied.add(p)

    for pattern, etype in _AUTO_PATTERNS:
        for m in pattern.finditer(text):
            start = _utf16_offset(text, m.start())
            end = _utf16_offset(text, m.end())
            if any(p in occupied for p in range(start, end)):
                continue
            new_spans.append(_Span(start=start, end=end, entity_type=etype))
            for p in range(start, end):
                occupied.add(p)

    return new_spans


def _build_offset_map(
    placeholder_text: str,
    pre_blocks: list,
    code_spans: list,
    links: list
) -> dict[int, int]:
    mapping = {}
    old_off = 0
    new_off = 0
    i = 0
    pt = placeholder_text

    while i < len(pt):
        mapping[old_off] = new_off

        m_pre = _RE_PH_PRE.match(pt, i)
        if m_pre:
            idx = int(m_pre.group(1))
            _, content = pre_blocks[idx]
            content = content.rstrip("\n")
            old_off += _utf16_len(m_pre.group(0))
            new_off += _utf16_len(content)
            i = m_pre.end()
            continue

        m_code = _RE_PH_CODE.match(pt, i)
        if m_code:
            idx = int(m_code.group(1))
            content = code_spans[idx]
            old_off += _utf16_len(m_code.group(0))
            new_off += _utf16_len(content)
            i = m_code.end()
            continue

        m_link = _RE_PH_LINK.match(pt, i)
        if m_link:
            idx = int(m_link.group(1))
            display, _ = links[idx]
            old_off += _utf16_len(m_link.group(0))
            new_off += _utf16_len(display)
            i = m_link.end()
            continue

        ch = pt[i]
        clen = _utf16_len(ch)
        old_off += clen
        new_off += clen
        i += 1

    mapping[old_off] = new_off
    return mapping


def _find_split_point(text: str, max_utf16_len: int) -> int:
    utf16_count = 0
    last_para = 0
    last_newline = 0

    for idx, ch in enumerate(text):
        clen = _utf16_len(ch)
        if utf16_count + clen > max_utf16_len:
            if last_para > 0:
                return last_para
            if last_newline > 0:
                return last_newline
            return idx

        utf16_count += clen

        if ch == "\n":
            if idx > 0 and text[idx - 1] == "\n":
                last_para = idx + 1
            last_newline = idx + 1

    return len(text)


def _shift_entities(entities: list[MessageEntity], offset: int) -> list[MessageEntity]:
    result = []
    for e in entities:
        new_offset = e.offset - offset
        if new_offset < 0:
            continue
        result.append(MessageEntity(
            type=e.type, offset=new_offset, length=e.length,
            url=e.url, language=e.language
        ))
    return result


def parse_entities(text: str) -> tuple[str, list[MessageEntity]]:
    text, pre_blocks, code_spans, links = _extract_protected(text)
    text = _strip_horizontal_rules(text)
    text, quote_line_ranges = _parse_blockquotes(text)
    text = _headings_to_bold(text)
    text = _bullets_to_dot(text)
    plain_text, spans = _parse_inline(text)

    final_chars = []
    entities = []
    offset = 0
    existing_spans_for_autodetect = []

    i = 0
    pt = plain_text

    while i < len(pt):
        m_pre = _RE_PH_PRE.match(pt, i)
        if m_pre:
            idx = int(m_pre.group(1))
            lang, content = pre_blocks[idx]
            content = content.rstrip("\n")
            content_len = _utf16_len(content)
            final_chars.append(content)
            entity_kwargs = {"type": "pre", "offset": offset, "length": content_len}
            if lang:
                entity_kwargs["language"] = lang
            entities.append(MessageEntity(**entity_kwargs))
            existing_spans_for_autodetect.append(_Span(start=offset, end=offset + content_len, entity_type="pre"))
            offset += content_len
            i = m_pre.end()
            continue

        m_code = _RE_PH_CODE.match(pt, i)
        if m_code:
            idx = int(m_code.group(1))
            content = code_spans[idx]
            content_len = _utf16_len(content)
            final_chars.append(content)
            entities.append(MessageEntity(type="code", offset=offset, length=content_len))
            existing_spans_for_autodetect.append(_Span(start=offset, end=offset + content_len, entity_type="code"))
            offset += content_len
            i = m_code.end()
            continue

        m_link = _RE_PH_LINK.match(pt, i)
        if m_link:
            idx = int(m_link.group(1))
            display, url = links[idx]
            display_len = _utf16_len(display)
            final_chars.append(display)
            entities.append(MessageEntity(type="text_link", offset=offset, length=display_len, url=url))
            existing_spans_for_autodetect.append(_Span(start=offset, end=offset + display_len, entity_type="text_link"))
            offset += display_len
            i = m_link.end()
            continue

        ch = pt[i]
        final_chars.append(ch)
        offset += _utf16_len(ch)
        i += 1

    final_text = "".join(final_chars)

    offset_map = _build_offset_map(plain_text, pre_blocks, code_spans, links)

    for span in spans:
        new_start = offset_map.get(span.start)
        new_end = offset_map.get(span.end)
        if new_start is not None and new_end is not None and new_end > new_start:
            etype = span.entity_type
            entities.append(MessageEntity(type=etype, offset=new_start, length=new_end - new_start))
            existing_spans_for_autodetect.append(_Span(start=new_start, end=new_end, entity_type=etype))

    if quote_line_ranges:
        lines = final_text.split("\n")
        line_starts = []
        off = 0
        for line in lines:
            line_starts.append(off)
            off += _utf16_len(line) + 1

        for qs, qe in quote_line_ranges:
            if qs < len(line_starts):
                q_start = line_starts[qs]
                if qe + 1 < len(line_starts):
                    q_end = line_starts[qe + 1] - 1
                else:
                    q_end = _utf16_len(final_text)
                if q_end > q_start:
                    entities.append(MessageEntity(type="blockquote", offset=q_start, length=q_end - q_start))

    auto_spans = _auto_detect(final_text, existing_spans_for_autodetect)
    for span in auto_spans:
        entities.append(MessageEntity(type=span.entity_type, offset=span.start, length=span.end - span.start))

    entities.sort(key=lambda e: (e.offset, -e.length))
    return final_text, entities


def split_with_entities(text: str, entities: list[MessageEntity], max_length: int = 4096) -> list[tuple[str, list[MessageEntity]]]:
    if _utf16_len(text) <= max_length:
        return [(text, entities)]

    chunks = []
    remaining_text = text
    remaining_entities = list(entities)
    global_offset = 0

    while remaining_text:
        if _utf16_len(remaining_text) <= max_length:
            shifted = _shift_entities(remaining_entities, global_offset)
            chunks.append((remaining_text, shifted))
            break

        split_idx = _find_split_point(remaining_text, max_length)
        chunk_text = remaining_text[:split_idx]
        chunk_utf16_len = _utf16_len(chunk_text)

        chunk_entities = []
        leftover_entities = []

        for e in remaining_entities:
            e_start = e.offset
            e_end = e.offset + e.length

            if e_end <= global_offset + chunk_utf16_len:
                chunk_entities.append(e)
            elif e_start < global_offset + chunk_utf16_len:
                new_len = (global_offset + chunk_utf16_len) - e_start
                chunk_entities.append(MessageEntity(
                    type=e.type, offset=e.offset, length=new_len,
                    url=e.url, language=e.language
                ))
                leftover_entities.append(MessageEntity(
                    type=e.type, offset=global_offset + chunk_utf16_len,
                    length=e.length - new_len, url=e.url, language=e.language
                ))
            else:
                leftover_entities.append(e)

        shifted = _shift_entities(chunk_entities, global_offset)
        chunks.append((chunk_text, shifted))

        global_offset += chunk_utf16_len
        remaining_text = remaining_text[split_idx:]
        remaining_entities = leftover_entities

    return chunks


def trim_to_limit(
    text: str,
    entities: list[MessageEntity] | None,
    max_length: int = 4096,
    suffix: str = "..."
) -> tuple[str, list[MessageEntity]]:
    entities = entities or []
    text_u16 = _utf16_len(text)
    suffix_u16 = _utf16_len(suffix)
    
    if text_u16 <= max_length:
        return text, entities
    
    cut_u16 = max_length - suffix_u16

    u16_count = 0
    cut_idx = len(text)
    for idx, ch in enumerate(text):
        clen = _utf16_len(ch)
        if u16_count + clen > cut_u16:
            cut_idx = idx
            break
        u16_count += clen

    trimmed = text[:cut_idx] + suffix

    kept: list[MessageEntity] = []
    for e in entities:
        if e.offset >= u16_count:
            continue
        if e.offset + e.length > u16_count:
            kept.append(MessageEntity(
                type=e.type,
                offset=e.offset,
                length=u16_count - e.offset,
                url=e.url,
                user=e.user,
                language=e.language,
                custom_emoji_id=e.custom_emoji_id,
                unix_time=e.unix_time,
                date_time_format=e.date_time_format
            ))
        else:
            kept.append(e)

    return trimmed, kept