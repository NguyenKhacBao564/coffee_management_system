"""Bounded camera work windows; scale silence is never a departure signal."""
import math

class EventGate:
    def __init__(self, config, state=None):
        if not (1 <= config['capture_seconds'] <= 180 and 1 <= config['max_inference_frames'] <= 360
                and 1 <= config['max_evidence_frames'] <= 12 and 1 <= config['signal_max_age_seconds'] <= 30
                and config['signal_rearm_gap_seconds'] >= config['capture_seconds']):
            raise ValueError('CAMERA_EVENT_POLICY_INVALID')
        if config.get('selection_mode') == 'plate_guided':
            fields = ('evidence_spacing_seconds', 'capture_hz', 'min_capture_seconds',
                      'success_min_plate_width', 'success_min_plate_height', 'success_min_sharpness',
                      'success_min_plate_score', 'success_plate_frames')
            if (any(isinstance(config.get(k), bool) or not isinstance(config.get(k), (int, float)) or
                    not math.isfinite(config[k]) or config[k] <= 0 for k in fields) or
                    not 2 <= config['success_plate_frames'] <= config['max_evidence_frames'] or
                    config['success_min_plate_score'] > 1 or config['capture_hz'] > 3 or
                    config['min_capture_seconds'] >= config['capture_seconds'] or
                    config['max_inference_frames'] < config['capture_seconds'] * config['capture_hz'] or
                    not 1 <= config.get('max_plate_calls', 0) <= 60 or not 1 <= config.get('max_ocr_calls', 0) <= 8):
                raise ValueError('CAMERA_EVENT_SELECTION_POLICY_INVALID')
        self.config = config
        self.state = state or {}
        self.state.setdefault('capture_until', 0)
        self.state.setdefault('preview_until', 0)
        self.state.setdefault('last_signal_observed', None)
        self.state.setdefault('last_signal_id', None)

    def signal(self, signal_id, observed, weight, now):
        if float(weight) < 1000 or not -2 <= now - observed <= self.config['signal_max_age_seconds']:
            return False
        if signal_id == self.state['last_signal_id']:
            return False
        previous = self.state['last_signal_observed']
        if previous is not None and observed <= previous:
            return False
        self.state['last_signal_id'] = signal_id
        self.state['last_signal_observed'] = observed
        # Silence merely re-arms capture; it is not a physical vehicle/session identity.
        if previous is not None and observed - previous <= self.config['signal_rearm_gap_seconds']:
            return False
        return self.trigger(now, 'scale_signal', signal_id)

    def trigger(self, now, origin, trigger_id):
        if now < self.state['capture_until']:
            return False  # Signals/buttons cannot extend or multiply the same window.
        self.state.update(capture_until=now + self.config['capture_seconds'],
                          trigger_at=now, trigger_origin=origin, trigger_id=trigger_id,
                          frame_count=0, evidence_count=0, inference_count=0, plate_model_calls=0, ocr_model_calls=0,
                          request_at=now, last_evidence_at=0,
                          completion_reason=None, completed_at=None, candidate_count=0, qualifying_plate_count=0,
                          capture_session_ids=[],
                          first_frame_seconds=None, first_evidence_seconds=None, suggestion_seconds=None)
        return True

    def finish(self, now, reason):
        self.state.update(capture_until=min(now, self.state['capture_until']),
                          completed_at=now, completion_reason=reason)

    def capturing(self, now):
        return now < self.state['capture_until']

    def preview(self, now):
        return now < self.state['preview_until']

    def connected(self, now):
        return self.capturing(now) or self.preview(now)
