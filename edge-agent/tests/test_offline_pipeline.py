from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

import cv2
import numpy as np
import pytest

from offline_vision.config import CameraConfig
from offline_vision.consensus import decide, normalize
from offline_vision.detectors import VehicleDetector
from offline_vision.evaluate import evaluate
from offline_vision.fixtures import FixtureOCR, FixturePlateDetector, FixtureVehicleDetector, create_fixture
from offline_vision.pipeline import run_pipeline
from offline_vision.ocr import PlateOCR
from offline_vision.sessions import SessionManager
from offline_vision.tracking import Tracker
from offline_vision.types import Detection
from offline_vision.video import VideoReader

ROI = [[.25,.4],[.8,.4],[.8,.98],[.25,.98]]


def config(**changes):
    return replace(CameraConfig("test-camera", ROI), plate_attempt_interval_seconds=1,
                   ocr_phase_seconds=(2, 4), repeat_crop_seconds=.8, plate_phase_backoff=0, **changes).validate()


def run_fixture(tmp_path, case, **options):
    video = create_fixture(tmp_path / "input", case)
    scenario = json.loads((tmp_path / "input/scenario.json").read_text())
    return run_pipeline(video,tmp_path / "result",options.pop("camera",config()), FixtureVehicleDetector(scenario), FixturePlateDetector(scenario), FixtureOCR(scenario),fixture=True,**options)


@pytest.mark.parametrize("case", ["no-vehicle", "outside-roi"])
def test_no_roi_vehicle_never_invokes_plate_or_ocr(tmp_path, case):
    report = run_fixture(tmp_path,case)
    assert report["sessions"] == []
    assert report["statistics"]["plate_detection_calls"] == report["statistics"]["ocr_model_calls"] == 0
    assert report["statistics"]["sampled_frames"] == 20 < report["statistics"]["decoded_frames"] == 100


def test_entry_exit_consensus_and_evidence(tmp_path):
    report = run_fixture(tmp_path,"enter-exit")
    assert len(report["sessions"]) == 1
    session = report["sessions"][0]
    assert session["proposed_plate"] == "51C12345"
    assert session["status"] == "needs_confirmation" and session["end_reason"] == "roi_exit"
    assert len(session["raw_ocr"]) == 3
    assert {read["raw"] for read in session["raw_ocr"]} == {"51C-123.45"}
    assert session["limits"]["ocr_stopped_after_consensus"] is True
    assert (tmp_path / "result" / session["evidence"]["overview"]).is_file()
    assert len(session["evidence"]["plate_crops"]) <= 4
    assert "start_utc" not in session
    assert report["statistics"]["accuracy"] is None and report["statistics"]["fully_correct_plates"] is None
    assert 'FIXTURE SCRIPTED' in (tmp_path / 'result/review.html').read_text()


def test_short_detection_dropout_keeps_one_session(tmp_path):
    report = run_fixture(tmp_path,"short-dropout")
    assert len(report["sessions"]) == 1
    assert report["sessions"][0]["proposed_plate"] == "51C12345"


def test_no_plate_keeps_useful_vehicle_and_overview(tmp_path):
    report = run_fixture(tmp_path,"no-plate")
    session = report["sessions"][0]
    assert session["recognition"] == "unknown" and session["proposed_plate"] is None
    assert session["plate_observations"] == session["raw_ocr"] == []
    for field in ["overview","annotated","vehicle_crop"]:
        assert cv2.imread(str(tmp_path / "result" / session["evidence"][field])).size > 0


def test_conflicting_ocr_budget_and_candidates(tmp_path):
    report = run_fixture(tmp_path,"conflicting-ocr",camera=config(max_ocr_reads=4,consistent_reads=3,max_saved_plate_crops=2,max_plate_attempts=5))
    session = report["sessions"][0]
    assert session["recognition"] == "unknown"
    assert {item["normalized"] for item in session["candidates"]} == {"51C12345","51C12845"}
    assert session["limits"]["ocr_model_calls"] == 4
    assert session["limits"]["plate_attempts"] == 5
    assert len(session["evidence"]["plate_crops"]) == 2
    times = sorted(read["media_seconds"] for read in session["raw_ocr"])
    assert all(b-a >= 1 for a,b in zip(times,times[1:]))


def test_media_clock_and_explicit_utc_only(tmp_path):
    anchor = datetime(2026,1,1,tzinfo=timezone.utc)
    report = run_fixture(tmp_path,"enter-exit",video_start_utc=anchor)
    session = report["sessions"][0]
    assert datetime.fromisoformat(session["start_utc"]).timestamp() == anchor.timestamp() + session["start_media_seconds"]
    video = tmp_path / "input/fixture.mp4"
    expected = json.loads(subprocess.check_output(["ffprobe","-v","error","-select_streams","v:0","-show_frames","-show_entries","frame=best_effort_timestamp_time","-of","json",str(video)]))["frames"]
    reader = VideoReader(video,2)
    frames = list(reader)
    assert all(frame.seconds == pytest.approx(float(expected[frame.index]["best_effort_timestamp_time"]), abs=1e-9) for frame in frames)


def test_track_id_can_change_without_duplicate_roi_session():
    cfg = config(tracking_gap_seconds=1,session_gap_seconds=4)
    tracker, sessions = Tracker(cfg), SessionManager(cfg)
    detection = Detection((210,80,450,315),"truck",.9,"fixture")
    for stamp in [0,.5,1,3,3.5]:
        sessions.update(tracker.update([detection],stamp,(360,640,3)),stamp,(360,640,3))
    assert len(sessions.sessions) == 1 and len(sessions.sessions[0].track_ids) == 2
    sessions.finish(4)
    assert sessions.sessions[0].ended == 4


def test_two_visible_vehicles_do_not_share_session():
    cfg = config(min_entry_observations=1)
    tracker, sessions = Tracker(cfg), SessionManager(cfg)
    detections = [Detection((180,100,300,310),"truck",.9,"fixture"),Detection((380,100,480,310),"truck",.9,"fixture")]
    for stamp in [0,.5]:
        links=sessions.update(tracker.update(detections,stamp,(360,640,3)),stamp,(360,640,3))
    assert len(sessions.sessions) == len(links) == 2
    assert len({session.session_id for session,_ in links}) == 2


def test_long_gap_makes_new_session_not_long_term_identity():
    cfg = config(min_entry_observations=1,tracking_gap_seconds=1,session_gap_seconds=3)
    tracker, sessions = Tracker(cfg), SessionManager(cfg)
    detection = Detection((210,80,450,315),"truck",.9,"fixture")
    for stamp in [0,1,5]:
        sessions.update(tracker.update([detection],stamp,(360,640,3)),stamp,(360,640,3))
    assert len(sessions.sessions) == 2
    assert sessions.sessions[0].end_reason == "detection_gap_expired"


@pytest.mark.parametrize("raw,expected", [("51c-123.45", "51C12345"),(" 51 C\n12345 ","51C12345"),("5IC-I234O", "5ICI234O"),("51C?12345", "51C?12345")])
def test_normalization_never_corrects_ambiguous_characters(raw, expected):
    assert normalize(raw) == expected


def test_same_frame_multiple_crops_not_multiple_consistent_observations():
    reads=[{"read_index":i,"media_seconds":0,"normalized":"51C12345"} for i in range(3)]
    assert decide(reads,3,.8)[0] is None


def test_ambiguous_candidates_same_frame_do_not_pass_consensus():
    reads=[{"read_index":i,"media_seconds":i//2,"normalized":"51C12345" if i%2==0 else "51C12845"} for i in range(6)]
    assert decide(reads,3,.8)[0] is None


@pytest.mark.parametrize("changes", [{"sample_hz":0},{"roi":[[0,0],[1,1],[0,1],[1,0]]},{"roi":[[0,0],[2,0],[1,1]]},{"camera_id":"../escape"},{"cpu_threads":32},{"consistent_reads":9,"max_ocr_reads":3}])
def test_config_rejects_invalid_or_unbounded_values(changes):
    with pytest.raises(ValueError): replace(CameraConfig("test",ROI),**changes).validate()


def test_evaluation_requires_exact_run_and_completed_manual_labels(tmp_path):
    report=run_fixture(tmp_path,"enter-exit")
    with pytest.raises(ValueError): evaluate(report,{"run_id":report["run_id"],"label_origin":"manual_review_required","roi_ground_truth_sessions":[]})
    labels={"run_id":report["run_id"],"label_origin":"manual_review","complete_clip_review":True,"roi_ground_truth_sessions":[{"start_media_seconds":1,"end_media_seconds":6,"plate_visible":True,"plate":"51C-12345","predicted_session_id":"s00001"}]}
    result=evaluate(report,labels)
    assert result["fully_correct_plates"] == 1 and result["full_plate_exact_match_rate"] == 1
    labels["run_id"]="wrong"
    with pytest.raises(ValueError): evaluate(report,labels)


def test_output_refuses_existing_folder(tmp_path):
    run_fixture(tmp_path,"no-plate")
    video=tmp_path / "input/fixture.mp4"
    with pytest.raises(FileExistsError):
        run_pipeline(video,tmp_path / "result",config(),None,None,None)


def test_vehicle_adapter_preserves_official_rgb_channel_order():
    class Net:
        def setInput(self,blob): self.blob=blob
        def forward(self): return np.zeros((1,1,85),np.float32)
    detector=VehicleDetector.__new__(VehicleDetector)
    detector.net=Net(); detector.threshold=.35
    detector.grid=np.zeros((1,2)); detector.strides=np.ones((1,1))
    image=np.full((4,4,3),[5,7,13],np.uint8)
    assert detector.detect(image,0) == []
    assert detector.net.blob[0,:,0,0].tolist() == [13,7,5]


def test_crnn_ctc_blank_and_repeat_decoding_and_two_line_call_cost():
    class Net:
        def setInput(self,blob): self.blob=blob
        def forward(self):
            result=np.full((5,1,37),-10,np.float32)
            for i,label in enumerate([2,2,0,2,3]): result[i,0,label]=10
            return result
    ocr=PlateOCR.__new__(PlateOCR); ocr.net=Net(); ocr.layout='auto'
    assert ocr.cost(np.zeros((50,100,3),np.uint8)) == 2
    assert ocr.cost(np.zeros((25,100,3),np.uint8)) == 1
    read=ocr.read(np.zeros((50,100,3),np.uint8))
    assert read.raw == '112\n112' and read.raw_lines == ['112','112']
    assert read.inference_calls == 2


def test_vfr_media_sampling_uses_pts_not_frame_index_divided_by_nominal_fps(tmp_path):
    base=create_fixture(tmp_path/'vfr-input','no-vehicle')
    video=tmp_path/'vfr.mp4'
    subprocess.run(['ffmpeg','-v','error','-i',str(base),'-vf',"setpts='if(lt(N,50),N/(10*TB),(5+(N-50)/5)/TB)'",'-fps_mode','vfr','-c:v','mpeg4',str(video)],check=True)
    pts=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_frames','-show_entries','frame=best_effort_timestamp_time','-of','json',str(video)]))['frames']
    frames=list(VideoReader(video,2))
    assert all(frame.seconds == pytest.approx(float(pts[frame.index]['best_effort_timestamp_time']),abs=1e-9) for frame in frames)
    assert frames[-1].seconds > 14 and frames[-1].index / 10 < 10


def test_ocr_cost_two_lines_respects_neural_call_budget(tmp_path):
    from offline_vision.types import OcrRead
    class OCR(FixtureOCR):
        def cost(self,crop): return 2
        def read(self,crop): return OcrRead('51C12345',.9,'two-line-fixture',inference_calls=2)
    video=create_fixture(tmp_path/'two-line','short-dropout')
    scenario=json.loads((tmp_path/'two-line/scenario.json').read_text())
    report=run_pipeline(video,tmp_path/'two-line-result',config(max_ocr_reads=5,consistent_reads=3),FixtureVehicleDetector(scenario),FixturePlateDetector(scenario),OCR(scenario),fixture=True)
    assert report['statistics']['ocr_model_calls'] == 4
    assert report['sessions'][0]['proposed_plate'] is None


def test_pinned_real_ocr_adapter_can_infer_on_local_synthetic_crop():
    folder=Path(__file__).resolve().parents[2]/'data/offline-vision/models'
    if not (folder/'manifest.json').exists():
        pytest.skip('Explicit fetch-models is required for this optional CPU model smoke test; never download in tests')
    crop=np.full((70,260,3),255,np.uint8)
    cv2.putText(crop,'51C12345',(8,50),cv2.FONT_HERSHEY_SIMPLEX,1.3,(0,0,0),2)
    read=PlateOCR(folder,'single-line').read(crop)
    assert isinstance(read.raw,str) and read.model == 'CRNN_EN_2021sep'
    assert read.inference_calls == 1 and (read.score is None or 0 <= read.score <= 1)


def test_explicit_completed_negative_manual_review_has_no_invented_accuracy(tmp_path):
    report=run_fixture(tmp_path,'no-vehicle')
    labels={'run_id':report['run_id'],'label_origin':'manual_review','complete_clip_review':True,'roi_ground_truth_sessions':[]}
    result=evaluate(report,labels)
    assert result['ground_truth_roi_vehicle_sessions'] == 0
    assert result['full_plate_exact_match_rate'] is result['vehicle_session_recall'] is None
    assert result['unmatched_predicted_sessions'] == []


def test_range_without_frames_is_error_not_no_vehicle_claim(tmp_path):
    with pytest.raises(ValueError,match='No sampled frames'):
        run_fixture(tmp_path,'no-vehicle',start=20)
