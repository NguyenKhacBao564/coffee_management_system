"""Manual-label-only evaluation; never infer correctness from confidence/consensus."""
import math

from .consensus import normalize


def evaluate(report: dict, labels: dict):
    if labels.get("run_id") != report["run_id"] or labels.get("label_origin") != "manual_review":
        raise ValueError("Labels must explicitly be manual_review for this exact run_id")
    truth = labels.get("roi_ground_truth_sessions")
    if not isinstance(truth, list):
        raise ValueError("A completed manual label list is required")
    if labels.get("complete_clip_review") is not True:
        raise ValueError("Mark complete_clip_review only after reviewing the full configured video range")
    known = {session["session_id"]:session for session in report["sessions"]}
    matched, exact, unknown, readable, matched_ids = 0,0,0,0,set()
    for item in truth:
        if type(item.get("plate_visible")) is not bool or not isinstance(item.get("start_media_seconds"), (float,int)):
            raise ValueError("Each truth session needs media interval and plate_visible")
        first,last = item["start_media_seconds"],item.get("end_media_seconds",-1)
        if not isinstance(last,(float,int)) or not math.isfinite(first) or not math.isfinite(last) or first < 0 or last < first:
            raise ValueError("Invalid label interval")
        identifier = item.get("predicted_session_id")
        if identifier is not None and (identifier not in known or identifier in matched_ids):
            raise ValueError("Predicted session IDs must exist and be matched one-to-one")
        if identifier is not None:
            prediction = known[identifier]
            if min(last,prediction["end_media_seconds"]) < max(first,prediction["start_media_seconds"]):
                raise ValueError("Manual label interval does not overlap the matched prediction")
            matched_ids.add(identifier); matched += 1
        plate = item.get("plate")
        if plate is not None:
            if not item["plate_visible"] or not isinstance(plate,str) or not normalize(plate):
                raise ValueError("Transcribed label must be visible and nonempty; null means unreadable")
            readable += 1
            prediction = known.get(identifier, {}).get("proposed_plate")
            if prediction is None:
                unknown += 1
            elif normalize(plate) == normalize(prediction):
                exact += 1
    visible = [item for item in truth if item["plate_visible"]]
    plates_found = sum(bool(known.get(item.get("predicted_session_id"),{}).get("plate_observations")) for item in visible)
    return {"run_id":report["run_id"], "label_origin":"manual_review", "fixture":report["fixture"],
            "scope":"ROI sessions in the full configured video range; not a full-frame vehicle detector AP benchmark",
            "ground_truth_roi_vehicle_sessions":len(truth), "matched_vehicle_sessions":matched,
            "missed_vehicle_sessions":len(truth)-matched, "unmatched_predicted_sessions":sorted(set(known)-matched_ids),
            "visible_plate_sessions":len(visible), "matched_sessions_with_plate_found":plates_found,
            "manually_readable_plates":readable, "fully_correct_plates":exact, "unknown_for_readable_plates":unknown,
            "full_plate_exact_match_rate":exact/readable if readable else None,
            "vehicle_session_recall":matched/len(truth) if truth else None, "plate_found_rate_for_visible_sessions":plates_found/len(visible) if visible else None}
