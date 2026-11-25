"""Bounded OCR ranking and aligned votes; proposals always require confirmation.

Grammar is a diagnostic subset of TT79/2024 Article37/Appendix04, not a
registration validator. See docs/offline-vision-d05i.md for sources/scope.
"""
import math
from collections import Counter, defaultdict

import numpy as np

from .consensus import normalize
from .ocr_diagnostic import edit_distance

DIGITS = '0123456789'
SERIES = 'ABCDEFGHKLMNPSTUVXYZ'
SPECIAL = ('CD', 'RM', 'HC', 'KT')


def patterns():
    result = []
    # Four-digit suffix is explicitly a legacy compatibility profile.
    for size in (4, 5):
        result.append((DIGITS, DIGITS, SERIES) + (DIGITS,) * size)
        for seri in SPECIAL:
            result.append((DIGITS, DIGITS, seri[0], seri[1]) + (DIGITS,) * size)
        # Blue motorcycle letter+digit series; not ordinary car series.
        result.append((DIGITS, DIGITS, 'ABCDEFGHKLM', '123456789') + (DIGITS,) * size)
    return result


def valid_prefix(text):
    return any(len(text) <= len(p) and all(c in allowed for c, allowed in zip(text, p)) for p in patterns())


def parse_plate(raw):
    text = normalize(raw)
    for p in patterns():
        if len(text) == len(p) and all(c in allowed for c, allowed in zip(text, p)):
            # Explicit matching resolves ambiguous digit-series/legacy lengths.
            for suffix_size in (5, 4):
                series = text[2:-suffix_size]
                allowed_series = series in SERIES and len(series) == 1 or series in SPECIAL or len(series) == 2 and series[0] in 'ABCDEFGHKLM' and series[1] in '123456789'
                if allowed_series and text[-suffix_size:].isdigit() and int(text[-suffix_size:]) > 0 and text[:2] != '00':
                    return {'normalized': text, 'province_digits': text[:2], 'series': series,
                            'number': text[-suffix_size:], 'profile': 'legacy_four_digit' if suffix_size == 4 else 'current_five_digit',
                            'province_allocation_verified': False, 'status': 'syntax_candidate_requires_confirmation'}
    return None


def rank_slots(probabilities, alphabet, pad='_', width=32, top_k=5):
    """Position-head likelihoods, NOT CTC. No O/0 or other substitutions."""
    probs = checked_probabilities(probabilities, len(alphabet))
    ranked = {}
    for pattern in patterns():
        if len(pattern) > len(probs):
            continue
        allowed = pattern + (pad,) * (len(probs) - len(pattern))
        beams = [('', 0.0)]
        for row, chars in zip(probs, allowed):
            choices = [(c, float(row[alphabet.index(c)])) for c in chars if c in alphabet and row[alphabet.index(c)] > 0]
            expanded = [(text + c, score + math.log(prob)) for text, score in beams for c, prob in choices]
            beams = sorted(expanded, key=lambda x: (-x[1], x[0]))[:width]
        for slots, score in beams:
            text = slots.rstrip(pad)
            if parse_plate(text):
                ranked[text] = max(score, ranked.get(text, -math.inf))
    return [{'normalized': text, 'log_score': score, 'label': 'đã ràng buộc định dạng', 'decoder': 'position_heads'}
            for text, score in sorted(ranked.items(), key=lambda x: (-x[1], x[0]))[:top_k]]


def checked_probabilities(values, vocabulary):
    probs = np.asarray(values, dtype=np.float64)
    if probs.ndim != 2 or probs.shape[1] != vocabulary or not np.isfinite(probs).all() or (probs < 0).any() or not np.allclose(probs.sum(axis=1), 1, atol=1e-4):
        raise ValueError('Expected finite normalized model probabilities')
    return probs


def ctc_beam(probabilities, characters, width=64, token_top_k=5, top_k=5, constrained=True):
    """CTC prefix beam: separate blank/nonblank masses, repeats and separators.

    Keeps token prefixes so punctuation/repeats retain CTC semantics. Bounded
    search is approximate; no beam score is advertised as calibrated confidence.
    """
    probs = checked_probabilities(probabilities, len(characters))
    beams = {(): (0.0, -math.inf)}
    for row in probs:
        indices = set(np.argsort(-row, kind='stable')[:token_top_k].tolist()) | {0}
        next_beams = {}
        def add(prefix, blank=-math.inf, nonblank=-math.inf):
            if not math.isfinite(blank) and not math.isfinite(nonblank):
                return
            old = next_beams.get(prefix, (-math.inf, -math.inf))
            next_beams[prefix] = (float(np.logaddexp(old[0], blank)), float(np.logaddexp(old[1], nonblank)))
        for prefix, (pb, pn) in beams.items():
            total = float(np.logaddexp(pb, pn))
            for index in indices:
                if row[index] <= 0:
                    continue
                logp = math.log(float(row[index]))
                if index == 0:
                    add(prefix, blank=total + logp)
                    continue
                repeated = bool(prefix) and index == prefix[-1]
                if repeated:
                    add(prefix, nonblank=pn + logp)
                new = prefix + (index,)
                raw = ''.join(characters[i] for i in new)
                text = normalize(raw)
                if len(raw) > 14 or len(text) > 9 or constrained and not valid_prefix(text):
                    continue
                add(new, nonblank=(pb if repeated else total) + logp)
        beams = dict(sorted(next_beams.items(), key=lambda x: (-float(np.logaddexp(*x[1])), x[0]))[:width])
    grouped = {}
    for prefix, masses in beams.items():
        raw = ''.join(characters[i] for i in prefix); text = normalize(raw)
        if not text or constrained and not parse_plate(text):
            continue
        score = float(np.logaddexp(*masses))
        previous = grouped.get(text)
        if previous:
            score = float(np.logaddexp(previous['log_score'], score))
            raw = previous['raw']  # deterministic first raw path; no GT selection
        grouped[text] = {'normalized': text, 'raw': raw, 'log_score': score,
                         'label': 'đã ràng buộc định dạng' if constrained else 'CTC beam chưa ràng buộc', 'decoder': 'CTC'}
    return sorted(grouped.values(), key=lambda x: (-x['log_score'], x['normalized']))[:top_k]


def align(anchor, text):
    """Levenshtein alignment against a prediction-only medoid."""
    n, m = len(anchor), len(text)
    cost = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1): cost[i][0] = i
    for j in range(m + 1): cost[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost[i][j] = min(cost[i-1][j-1] + (anchor[i-1] != text[j-1]), cost[i-1][j] + 1, cost[i][j-1] + 1)
    i, j = n, m; operations = []
    while i or j:
        if i and j and cost[i][j] == cost[i-1][j-1] + (anchor[i-1] != text[j-1]):
            operations.append(('char', i-1, text[j-1])); i -= 1; j -= 1
        elif i and cost[i][j] == cost[i-1][j] + 1:
            operations.append(('char', i-1, None)); i -= 1
        else:
            operations.append(('insert', i, text[j-1])); j -= 1
    chars = [None] * n; insertions = defaultdict(str)
    for kind, pos, char in reversed(operations):
        if kind == 'char': chars[pos] = char
        else: insertions[pos] += char
    return chars, dict(insertions)


def unique_frames(reads):
    tracks = {r['track_id'] for r in reads}
    if len(tracks) > 1 or tracks and any(not isinstance(t, str) or not t for t in tracks):
        raise ValueError('Cannot vote across tracks or unknown track identity')
    groups = defaultdict(list)
    for read in reads:
        if not math.isfinite(read['media_seconds']): raise ValueError('Nonfinite media time')
        groups[read['media_seconds']].append(read)
    result = []
    for seconds, group in sorted(groups.items()):
        choices = {normalize(r['normalized']) for r in group}
        result.append({'media_seconds': seconds, 'normalized': next(iter(choices)) if len(choices) == 1 else '',
                       'same_frame_disagreement': len(choices) > 1, 'evidence': group})
    return result


def character_vote(reads, required=3, ratio=2/3, character_support=2):
    if required < 2 or character_support < 2 or not .5 < ratio <= 1:
        raise ValueError('Vote must require multiple frames and a strict majority')
    observations = unique_frames(reads)
    texts = [r['normalized'] for r in observations]; nonempty = [t for t in texts if t]
    if len(observations) < required or len(nonempty) < required:
        return {'proposal': None, 'reason': 'insufficient_distinct_frames', 'observations': observations, 'columns': []}
    anchor = min(set(nonempty), key=lambda a: (sum(edit_distance(a, b) for b in nonempty), a))
    aligned = [align(anchor, text) for text in texts]
    columns = []
    for pos in range(len(anchor) + 1):
        size = max(len(ins.get(pos, '')) for _, ins in aligned)
        for offset in range(size):
            columns.append([ins.get(pos, '')[offset] if offset < len(ins.get(pos, '')) else None for _, ins in aligned])
        if pos < len(anchor): columns.append([chars[pos] for chars, _ in aligned])
    details, proposal, supported = [], [], True
    for column in columns:
        counts = Counter(column); ordered = sorted(counts.items(), key=lambda x: (-x[1], str(x[0])))
        winner, support = ordered[0]
        unique = len(ordered) == 1 or support > ordered[1][1]
        accepted = unique and support >= character_support and support / len(texts) >= ratio
        supported &= accepted
        if winner is not None: proposal.append(winner)
        details.append({'votes': [{'character': c, 'frames': count} for c, count in ordered], 'winner': winner, 'accepted': accepted})
    text = ''.join(proposal)
    return {'proposal': text if supported and parse_plate(text) else None,
            'unconstrained_vote': text, 'reason': 'character_proposal_requires_confirmation' if supported and parse_plate(text) else 'conflicting_or_outside_format',
            'anchor': anchor, 'observations': observations, 'columns': details}
