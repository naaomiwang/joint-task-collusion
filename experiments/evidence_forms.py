"""Same evidence, two forms: verbatim raw-log excerpts vs free-text claims.

For a controlled Bob, build five messages of at most 200 characters from his raw
log in two forms that carry identical content:

- verbatim: contiguous excerpts of the raw-log string, copied exactly;
- claim: the field text visible in each excerpt, restated as plain claims
  ("My final answer: ...", "My query: ..."), without the log's JSON.

Excerpts sit over the answer-bearing fields of each task type, in a fixed priority
order. Where a claim would exceed 200 characters the excerpt is shortened until
both forms fit, so each claim carries exactly the text its excerpt shows.
Deterministic; no model calls.
"""

import json
import re

MESSAGE_COUNT = 5
MESSAGE_CHARS = 200

# (tool, part, key, label, take) per task type, highest priority first.
# take: "head" starts the excerpt at the field's key, "tail" ends it at the value's end.
TARGETS = {
    "data_search": [
        ("save_final_answer", "arguments", "answer", "My final answer", "head"),
        ("query_database", "arguments", "sql", "My query", "head"),
        ("save_final_answer", "arguments", "reasoning", "My reasoning", "head"),
        ("query_database", "result", "rows", "Query result rows", "head"),
    ],
    "code_analysis": [
        ("save_final_answer", "arguments", "answer", "My final answer", "head"),
        ("save_final_answer", "arguments", "reasoning", "My reasoning", "head"),
        ("run_tests", "result", "toolchain_output", "Test output", "tail"),
        ("write_test_file", "arguments", "content", "My test code", "head"),
    ],
    "record_extraction": [
        ("save_final_answer", "arguments", "answer", "My final answer", "head"),
        ("save_final_answer", "arguments", "reasoning", "My reasoning", "head"),
        ("resolve_records", "arguments", "records", "Records I selected", "head"),
        ("resolve_records", "result", "items", "Record IDs returned", "head"),
    ],
}


def serialize(steps: list[dict]) -> tuple[str, list[tuple]]:
    """The raw-log string as get_log returns it, with each field's spans.

    Returns (text, fields) where each field is (tool, part, key, key_start, value_start, end).
    """
    out, pos, fields = ["["], 1, []
    for i, step in enumerate(steps):
        if i:
            out.append(","); pos += 1
        out.append("{"); pos += 1
        for j, (k, v) in enumerate(step.items()):
            if j:
                out.append(","); pos += 1
            head = json.dumps(k, ensure_ascii=False) + ":"
            out.append(head); pos += len(head)
            if isinstance(v, dict) and k in ("arguments", "result"):
                out.append("{"); pos += 1
                for m, (kk, vv) in enumerate(v.items()):
                    if m:
                        out.append(","); pos += 1
                    key_start = pos
                    kh = json.dumps(kk, ensure_ascii=False) + ":"
                    out.append(kh); pos += len(kh)
                    text = json.dumps(vv, ensure_ascii=False, separators=(",", ":"))
                    fields.append((step.get("tool"), k, kk, key_start, pos, pos + len(text)))
                    out.append(text); pos += len(text)
                out.append("}"); pos += 1
            else:
                text = json.dumps(v, ensure_ascii=False, separators=(",", ":"))
                out.append(text); pos += len(text)
        out.append("}"); pos += 1
    out.append("]")
    return "".join(out), fields


def _unescape(fragment: str) -> str:
    """Decode a possibly truncated JSON string fragment into plain text."""
    fragment = fragment.strip('"')
    fragment = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), fragment)
    return (fragment.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')
            .replace("\\\\", "\\").rstrip("\\"))


TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null')


def _json_view(raw: str, v_start: int, v_end: int) -> tuple[str, list[int]] | None:
    """A field's value as JSON text plus a map from each of its characters to raw offsets.

    A list or object maps one to one. A string that itself holds JSON (data-search
    answers are stored this way) is decoded, and each decoded character is mapped
    back to its escaped position in the raw log. Plain strings return None.
    """
    value = raw[v_start:v_end]
    if not value.startswith('"'):
        return value, list(range(v_start, v_end + 1))
    try:
        inner = json.loads(value)
        if not isinstance(inner, str) or inner.lstrip()[:1] not in ("[", "{"):
            return None
        json.loads(inner)
    except (json.JSONDecodeError, TypeError):
        return None
    offsets, pos = [], v_start + 1
    for ch in inner:
        offsets.append(pos)
        pos += len(json.dumps(ch, ensure_ascii=False)) - 2
    offsets.append(pos)
    return (inner, offsets) if pos == v_end - 1 else None


def _structured_text(view: tuple[str, list[int]], a: int, b: int) -> str:
    """Restate the part of a JSON value visible in raw range [a, b) as 'key: v1, v2; ...'.

    The whole value is tokenized, so keys are known even when only their values are
    visible, and a token cut by the excerpt's edge contributes only its visible part.
    """
    text, offsets = view
    keyed: dict[str, list[str]] = {}
    plain: list[str] = []
    for m in TOKEN.finditer(text):
        inside = [i for i in range(m.start(), m.end()) if offsets[i] >= a and offsets[i + 1] <= b]
        if not inside or text[m.end():m.end() + 1] == ":":
            continue
        piece = text[inside[0]:inside[-1] + 1]
        if m.group().startswith('"'):
            piece = _unescape(piece)
        if not piece:
            continue
        key = re.search(r'"([^"\\]+)":\s*$', text[:m.start()])
        (keyed.setdefault(key.group(1), []) if key else plain).append(piece)
    parts = [f"{k}: {', '.join(v)}" for k, v in keyed.items()]
    if plain:
        parts.append("; ".join(plain))
    return "; ".join(parts)


def _claim_piece(raw: str, field: tuple, start: int, end: int, label: str) -> str:
    """The claim for the part of one field's value that lies inside [start, end)."""
    _, _, key, _, v_start, v_end = field
    a, b = max(start, v_start), min(end, v_end)
    if b <= a:
        return ""
    view = _json_view(raw, v_start, v_end)
    text = _structured_text(view, a, b) if view else _unescape(raw[a:b])
    text = " ".join(text.split())
    if not text:
        return ""
    lead = "…" if a > v_start else ""
    trail = "…" if b < v_end else ""
    return f"{label}: {lead}{text}{trail}"


def _claim_for_window(raw: str, fields: list[tuple], labels: dict, start: int, end: int) -> str:
    pieces = []
    for f in fields:
        label = labels.get((f[0], f[1], f[2]))
        if label and f[3] < end and f[5] > start:
            piece = _claim_piece(raw, f, start, end, label)
            if piece:
                pieces.append(piece)
    return " | ".join(pieces)


def build(steps: list[dict], task_type: str) -> dict | None:
    """Both forms for one raw log, or None if five excerpts cannot be placed."""
    raw, fields = serialize(steps)
    targets = TARGETS.get(task_type)
    if not targets:
        return None
    labels = {(t, p, k): label for t, p, k, label, _ in targets}
    # The last occurrence of each target field (agents may query more than once).
    chosen = []
    for tool, part, key, label, take in targets:
        matches = [f for f in fields if f[:3] == (tool, part, key)]
        if matches:
            chosen.append((matches[-1], take))

    windows: list[list[int]] = []
    covered: list[tuple[int, int]] = []

    def free(s, e):
        return all(e <= cs or s >= ce for cs, ce in covered)

    # Round 1: one excerpt per target; round 2+: continue each field where it left off.
    cursor = {}
    for round_ in range(MESSAGE_COUNT):
        for field, take in chosen:
            if len(windows) == MESSAGE_COUNT:
                break
            _, _, _, k_start, v_start, v_end = field
            if round_ == 0:
                s = max(0, v_end - MESSAGE_CHARS) if take == "tail" else k_start
            else:
                s = cursor.get(field)
                if s is None or s >= v_end or take == "tail":
                    continue
            e = min(len(raw), s + MESSAGE_CHARS)
            # Shorten until the claim fits in one message.
            while e > s:
                claim = _claim_for_window(raw, fields, labels, s, e)
                if len(claim) <= MESSAGE_CHARS:
                    break
                e -= max(1, len(claim) - MESSAGE_CHARS)
            if e <= s or not free(s, e) or not claim:
                continue
            windows.append([s, e])
            covered.append((s, e))
            cursor[field] = e
        if len(windows) == MESSAGE_COUNT:
            break
    if len(windows) < MESSAGE_COUNT:
        return None
    verbatim = [raw[s:e] for s, e in windows]
    claims = [_claim_for_window(raw, fields, labels, s, e) for s, e in windows]
    return {"verbatim": verbatim, "claim": claims, "windows": windows}
