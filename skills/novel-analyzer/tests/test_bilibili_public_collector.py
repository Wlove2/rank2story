"""Conservative public Bilibili caption validation: no network in tests."""
import importlib.util
import sys
import unittest
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "scripts" / "collect_bilibili_public_videos.py"
sys.path.insert(0, str(path.parent))
spec = importlib.util.spec_from_file_location("bili_public_collector_under_test", path)
collector = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = collector
spec.loader.exec_module(collector)


def video(*, duration=600, last_end=600, caption_text=None):
    return {
        "bvid": "BV1Nfby6kELw",
        "title": "2026年热门网文书单推荐",
        "author": "读者编辑",
        "author_id": 334,
        "pubdate": 1786792102,
        "duration": duration,
        "engagement": {"views": 1520, "likes": 100},
        "player_code": 0,
        "subtitles": [{
            "lang": "ai-zh", "segments": 100,
            "first_start": 3, "last_end": last_end,
            "content": caption_text or ("这是一段完整的实际书单内容。" * 30),
        }],
    }


class BilibiliPublicCollectorTests(unittest.TestCase):
    def test_complete_verified_public_track_is_admitted(self):
        row = collector.normalize_video(video())
        self.assertTrue(row["content_complete"])
        self.assertEqual(row["primary_signal_type"], "curator_roundup")
        self.assertEqual(row["subtitle_end_coverage_ratio"], 1)
        self.assertEqual(row["source_url"], "https://www.bilibili.com/video/BV1Nfby6kELw")

    def test_cutoff_track_cannot_be_marked_complete(self):
        row = collector.normalize_video(video(duration=600, last_end=330))
        self.assertFalse(row["content_complete"])
        self.assertFalse(row["signal_eligible"])
        self.assertEqual(row["incomplete_reason"], "missing_or_partial_usable_public_caption")

    def test_queries_are_interleaved_for_source_diversity(self):
        self.assertEqual(
            collector.interleave_queries([["a", "b", "c"], ["b", "d"], ["e"]], 5),
            ["a", "b", "e", "d", "c"],
        )
        self.assertEqual(collector.interleave_queries([], 5), [])

    def test_resume_keeps_real_screened_records_and_source_bound(self):
        import tempfile
        import json
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "public_videos.json"
            source_row = collector.normalize_video(video())
            path.write_text(json.dumps({
                "source_id": collector.SOURCE_ID,
                "discovery": {"discovered_unique_entries": 139, "screened_entries": 1},
                "entries": [source_row, source_row],
            }), encoding="utf-8")
            records, lower_bound = collector.previously_screened(Path(temporary))
            self.assertEqual(len(records), 1)
            self.assertEqual(lower_bound, 139)
            self.assertEqual(records[0]["bvid"], "BV1Nfby6kELw")

    def test_caption_exceeding_video_duration_is_rejected(self):
        sample = video(duration=600, last_end=1250)
        self.assertFalse(collector.normalize_video(sample)["content_complete"])

    def test_nonexistent_and_teaser_tracks_are_rejected(self):
        sample = video()
        sample["subtitles"] = []
        self.assertFalse(collector.normalize_video(sample)["content_complete"])
        sample["subtitles"] = [{"content": "预告" * 40, "first_start": 0, "last_end": 600}]
        self.assertFalse(collector.normalize_video(sample)["content_complete"])

    def test_video_without_real_public_metrics_is_incomplete(self):
        sample = video()
        sample["engagement"] = {}
        self.assertFalse(collector.normalize_video(sample)["content_complete"])
        sample["engagement"] = {"likes": 0}
        sample["player_code"] = -101
        self.assertFalse(collector.normalize_video(sample)["content_complete"])

    def test_no_signal_cannot_count_as_demand(self):
        sample = video()
        sample["title"] = "今天下雨了"
        sample["subtitles"][0]["content"] = "天气晴朗，继续散步。" * 30
        self.assertFalse(collector.normalize_video(sample)["content_complete"])

    def test_public_numeric_author_id_audits_without_exception(self):
        import importlib.util
        import json
        import tempfile
        from pathlib import Path
        social_path = path.with_name("social_evidence.py")
        social_spec = importlib.util.spec_from_file_location("numeric_author_social_audit", social_path)
        social = importlib.util.module_from_spec(social_spec)
        sys.modules[social_spec.name] = social
        social_spec.loader.exec_module(social)
        row = collector.normalize_video(video())
        self.assertTrue(row["content_complete"])
        with tempfile.TemporaryDirectory() as temporary:
            note_file = Path(temporary) / "public_videos.json"
            note_file.write_text(json.dumps({"entries": [row]}, ensure_ascii=False), encoding="utf-8")
            audit = social.audit_social_files(collector.SOURCE_ID, [note_file])
        self.assertEqual(audit["signal_eligible_entries"], 1)
        self.assertEqual(audit["unique_accounts"], 1)

    def test_screened_url_count_deduplicates_live_batches(self):
        import json
        import tempfile
        import importlib.util
        social_path = path.with_name("social_evidence.py")
        spec = importlib.util.spec_from_file_location("social_screening_dedup_test", social_path)
        social = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = social
        spec.loader.exec_module(social)
        with tempfile.TemporaryDirectory() as folder:
            paths = []
            for idx, bv_ids in enumerate((["BV1Nfby6kELw", "BV1LSMp62EYX"], ["BV1LSMp62EYX", "BV1Gph56kEqu"])):
                out = Path(folder) / f"batch_{idx}.json"
                out.write_text(json.dumps({
                    "discovery": {"discovered_unique_entries": 15, "screened_entries": 2},
                    "entries": [{"source_url": f"https://www.bilibili.com/video/{bvid}", "content_complete": False} for bvid in bv_ids],
                }), encoding="utf8")
                paths.append(out)
            audit = social.audit_social_files(collector.SOURCE_ID, paths)
            self.assertEqual(audit["screened_entries"], 3)
            self.assertEqual(audit["discovered_unique_entries"], 15)

    def test_per_account_cap_preserves_records_but_excludes_over_quota(self):
        import tempfile
        import json
        import importlib.util
        social_path = path.with_name("social_evidence.py")
        spec = importlib.util.spec_from_file_location("social_account_cap_audit", social_path)
        social = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = social
        spec.loader.exec_module(social)
        rows = []
        for i, bvid in enumerate((
            "BV1Nfby6kELw", "BV1LSMp62EYX", "BV1Gph56kEqu", "BV1qoht6dExu",
        )):
            item = video()
            item["bvid"] = bvid
            item["author_id"] = 101 if i < 3 else 202
            rows.append(collector.normalize_video(item))
        with tempfile.TemporaryDirectory() as folder:
            path_json = Path(folder) / "live.json"
            path_json.write_text(json.dumps({"entries": rows}), encoding="utf8")
            audit = social.audit_social_files(
                collector.SOURCE_ID, [path_json], max_entries_per_account=2
            )
        self.assertEqual(audit["complete_content_entries"], 4)
        self.assertEqual(audit["signal_eligible_entries"], 3)
        self.assertEqual(audit["excluded_over_account_cap"], 1)
        self.assertEqual(audit["unique_accounts"], 2)
        self.assertEqual(audit["max_entries_per_account"], 2)

    def test_invalid_video_id_fails(self):
        sample = video()
        sample["bvid"] = "invalid%secret"
        with self.assertRaisesRegex(ValueError, "INVALID_BVID"):
            collector.normalize_video(sample)


if __name__ == "__main__":
    unittest.main()
