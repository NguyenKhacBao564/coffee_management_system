import re


def normalize(raw: str) -> str:
    # Presentation normalization only. Never swap O/0, I/1, B/8, add or drop letters.
    return re.sub(r"[\s.\-]", "", raw.upper())


def candidates(reads: list[dict]) -> list[dict]:
    grouped = {}
    for read in reads:
        text = read["normalized"]
        if not text:
            continue
        group = grouped.setdefault(text, {"normalized": text, "observation_seconds": [], "read_indices": []})
        group["read_indices"].append(read["read_index"])
        if read["media_seconds"] not in group["observation_seconds"]:
            group["observation_seconds"].append(read["media_seconds"])
    for group in grouped.values():
        group["consistent_observations"] = len(group["observation_seconds"])
    return sorted(grouped.values(), key=lambda c: (-c["consistent_observations"], c["normalized"]))


def decide(reads, required: int, ratio: float):
    ranked = candidates(reads)
    if not ranked:
        return None, "no_readable_text", ranked
    winner = ranked[0]
    # Empty reads remain in the denominator. Different crops from one frame count once.
    total = max(len({r["media_seconds"] for r in reads}), sum(c["consistent_observations"] for c in ranked))
    unique = len(ranked) == 1 or winner["consistent_observations"] > ranked[1]["consistent_observations"]
    eligible = re.fullmatch(r"[A-Z0-9]{5,12}", winner["normalized"]) is not None
    if eligible and unique and winner["consistent_observations"] >= required and winner["consistent_observations"] / max(1, total) >= ratio:
        return winner["normalized"], "consistent_proposal_requires_confirmation", ranked
    return None, "conflicting_or_insufficient_reads", ranked
