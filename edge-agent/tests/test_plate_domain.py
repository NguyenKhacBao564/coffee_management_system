import itertools
import math

import numpy as np
import pytest

from offline_vision.plate_domain import parse_plate, rank_slots, ctc_beam, character_vote, unique_frames, align


@pytest.mark.parametrize('raw,seri,profile', [('29K-527.55', 'K', 'current_five_digit'),
    ('49c02655', 'C', 'current_five_digit'), ('51A1234', 'A', 'legacy_four_digit'),
    ('51RM01234', 'RM', 'current_five_digit'), ('29A112345', 'A1', 'current_five_digit')])
def test_domain_parser(raw, seri, profile):
    result = parse_plate(raw)
    assert result['series'] == seri and result['profile'] == profile
    assert result['province_allocation_verified'] is False


@pytest.mark.parametrize('raw', ['L9C02655', '49I02655', '车52755', '49C00000', '00A12345', '49C0265O', '80NG12301'])
def test_invalid_or_unsupported_not_rewritten(raw):
    assert parse_plate(raw) is None


def test_slots_rank_repeated_characters_and_do_not_need_ground_truth():
    alphabet = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_'
    probs = np.full((10, len(alphabet)), 1e-6)
    for i, c in enumerate('L9C02655__'): probs[i, alphabet.index(c)] = .9
    probs[0, alphabet.index('4')] = .09
    probs /= probs.sum(axis=1, keepdims=True)
    ranked = rank_slots(probs, alphabet)
    assert ranked[0]['normalized'] == '49C02655' and ranked[0]['label'] == 'đã ràng buộc định dạng'
    assert ranked[0]['log_score'] <= 0


def test_ctc_beam_matches_exhaustive_paths_with_repeats_and_blank():
    chars = ['blank', '4', '9']; p = np.array([[.2,.5,.3],[.4,.5,.1],[.3,.2,.5]])
    exact = {}
    for path in itertools.product(range(3), repeat=3):
        text = ''.join(chars[c] for i,c in enumerate(path) if c and (i == 0 or path[i-1] != c))
        if text: exact[text] = exact.get(text, 0) + np.prod([p[i,c] for i,c in enumerate(path)])
    beam = ctc_beam(p, chars, width=200, token_top_k=3, top_k=100, constrained=False)
    assert {r['normalized']: math.exp(r['log_score']) for r in beam} == pytest.approx(exact)


def test_ctc_constraint_ranks_probabilities_preserves_double_digits():
    chars = ['blank'] + list('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ.- ')
    raw = '49C02655'; p = np.full((len(raw)*2, len(chars)), 1e-8)
    for i,c in enumerate(raw): p[i*2,chars.index(c)] = .99; p[i*2+1,0] = .99
    p /= p.sum(axis=1,keepdims=True)
    assert ctc_beam(p,chars)[0]['normalized'] == raw


def reads(*texts):
    return [{'track_id': 't1', 'media_seconds': i, 'normalized': t} for i,t in enumerate(texts)]


def test_character_vote_recovers_from_distinct_position_errors_without_exact_winner():
    r=character_vote(reads('49C0265O','49CO2655','49C026S5'))
    assert r['proposal'] == '49C02655'
    assert all(c['accepted'] for c in r['columns'])


def test_alignment_supports_insertions_and_deletions():
    chars,ins=align('49C02655','49CX02655')
    assert ''.join(chars) == '49C02655' and ins == {3:'X'}
    assert character_vote(reads('49C02655','49C02655','49CX02655'))['proposal'] == '49C02655'
    assert character_vote(reads('49C02655','49C02655','49C2655'))['proposal'] == '49C02655'


@pytest.mark.parametrize('strings', [('49C02655','49C02655'), ('49C02655','',''), ('49C02655','29C02655','39C02655')])
def test_insufficient_or_tied_is_unknown(strings):
    assert character_vote(reads(*strings))['proposal'] is None


def test_duplicate_frames_do_not_supply_independent_votes_and_mixed_tracks_rejected():
    r=reads('49C02655','49C02655','49C02655')
    for v in r:v['media_seconds']=1
    assert character_vote(r)['proposal'] is None
    r[1]['normalized']='29C02655'
    assert unique_frames(r)[0]['same_frame_disagreement'] and unique_frames(r)[0]['normalized'] == ''
    r[1]['track_id']='t2'
    with pytest.raises(ValueError, match='tracks'): character_vote(r)


def test_probabilities_invalid_fail_closed():
    with pytest.raises(ValueError): ctc_beam(np.array([[float('nan'),1]]), ['blank','4'])


def test_unknown_track_and_unsafe_vote_parameters_rejected():
    r=reads('49C02655','49C02655','49C02655');r[0]['track_id']=None
    with pytest.raises(ValueError,match='tracks'):character_vote(r)
    with pytest.raises(ValueError,match='majority'):character_vote([],required=1)
