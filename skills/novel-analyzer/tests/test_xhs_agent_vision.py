"""No-network regression tests for Agent-native XHS vision and resume."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import collect_xiaohongshu_public_notes as xhs
import xiaohongshu_local_vision as vision


class XhsAgentVisionTests(unittest.TestCase):
    def test_staging_and_partial_then_complete_agent_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            url = "https://www.xiaohongshu.com/explore/" + "1" * 24
            signed = url.replace("/explore/", "/search_result/") + "?xsec_token=NOT_TO_BE_STORED&xsec_source=pc"
            search = [{"url": signed, "title": "书荒求文短篇小说",
                       "author": "读者", "published_at": "2026-10-17", "likes": 10}]
            note = {
                "url": url, "title": search[0]["title"],
                "description": "希望推荐真正有情节张力的短篇小说，尤其喜欢有完整结局的作品。" * 5,
                "note_present": True, "images_total": 2, "videos": 0,
            }
            seen = []
            def cli(prefix, args, timeout):
                seen.append(args)
                if args[:2] == ["xiaohongshu", "search"]:
                    return 0, json.dumps(search, ensure_ascii=False)
                if args[0] == "browser" and args[2] == "eval":
                    return 0, json.dumps(note, ensure_ascii=False)
                return 0, ""

            def stage(prefix, session, cli, expected, media_dir):
                self.assertEqual(expected, 2)
                records = []
                for idx in range(2):
                    payload = b"\x89PNG\r\n\x1a\n" + bytes([idx + 1]) * 5500
                    digest = hashlib.sha256(payload).hexdigest()
                    media_dir.mkdir(exist_ok=True)
                    (media_dir / (digest + ".png")).write_bytes(payload)
                    records.append({
                        "index": idx, "image_sha256": digest,
                        "image_path": "media/" + digest + ".png",
                        "text": "",
                    })
                return records

            with patch.object(xhs, "opencli_argv", return_value=["cli"]), \
                 patch.object(xhs, "run_cli", side_effect=cli), \
                 patch.object(xhs, "stage_public_gallery", side_effect=stage):
                a=xhs.collect(folder, ["小说 书荒"], limit=8, max_notes=2,
                              timeout=20, agent_vision=True, resume=True)
                self.assertEqual(len(a["entries"]), 1)
                self.assertFalse(a["entries"][0]["content_complete"])
                raw = (folder/"public_notes.json").read_text(encoding="utf-8")
                qraw = (folder/"agent_vision_queue.json").read_text(encoding="utf-8")
                self.assertNotIn("xsec_token", raw+qraw)
                self.assertEqual(len(json.loads(qraw)["images"]), 2)
                again=xhs.collect(folder, ["小说 书荒"], limit=8, max_notes=2,
                                  timeout=20, agent_vision=True, resume=True)
                self.assertEqual(len(again["entries"]), 1)
                self.assertEqual(len(json.loads((folder/"agent_vision_queue.json").read_text())["images"]),2)

            queue=json.loads(qraw)
            queue["images"][0]["text"]="图片真实文字描述：第一张书单封面与情节摘录，内容完整可辨。"
            xhs.save_json(folder/"agent_vision_queue.json", queue)
            partial=xhs.import_agent_vision(folder)
            self.assertEqual(partial["entries"][0]["images_read"],1)
            self.assertFalse(partial["entries"][0]["content_complete"])
            queue["images"][1]["text"]="图片真实文字描述：第二张作品角色和结局讨论，逐项阅读完毕。"
            xhs.save_json(folder/"agent_vision_queue.json", queue)
            complete=xhs.import_agent_vision(folder)
            self.assertTrue(complete["entries"][0]["content_complete"])
            self.assertEqual(complete["entries"][0]["images_read"],2)
            self.assertTrue(complete["entries"][0]["signal_eligible"])
            again=xhs.import_agent_vision(folder)
            self.assertEqual(again["entries"][0]["full_text"],complete["entries"][0]["full_text"])

            media=folder/queue["images"][0]["image_path"]
            media.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError,"HASH_MISMATCH"):
                xhs.import_agent_vision(folder)

    def test_proxy_configuration_is_not_overridden(self):
        class Response:
            headers={"Content-Type": "image/jpeg"}
            def __enter__(self):return self
            def __exit__(self,*args):return None
            def read(self,size):return b"\xff\xd8" + b"A"*5500
        with patch.object(vision.urllib.request, "urlopen", return_value=Response()) as mocked:
            b=vision.safe_image_bytes("https://abc.xhscdn.com/secure-image.jpg")
            self.assertEqual(len(b),5502)
            self.assertTrue(mocked.called)

    def test_import_rejects_missing_run_and_invalid_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "SCAN_AND_QUEUE_REQUIRED"):
                xhs.import_agent_vision(Path(d))


class OpencliWindowsShimTests(unittest.TestCase):
    def test_existing_direct_node_wrapper(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            node = base / "node.exe"
            script = base / "cli.js"
            node.touch()
            script.touch()
            shim = base / "opencli.cmd"
            shim.write_text(f'@echo off\n"{node}" "{script}" %*\n', encoding="utf-8")
            self.assertEqual(xhs.resolve_windows_opencli_shim(shim), [str(node), str(script)])

    def test_npm_cmd_shim_with_neighbor_node(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            script = base / "node_modules" / "@jackwener" / "opencli" / "dist" / "main.js"
            script.parent.mkdir(parents=True)
            script.touch()
            node = base / "node.exe"
            node.touch()
            shim = base / "opencli.cmd"
            shim.write_text(
                '@ECHO off\nSETLOCAL\nCALL :find_dp0\n'
                'IF EXIST "%dp0%\\node.exe" (\n'
                '  SET "_prog=%dp0%\\node.exe"\n'
                ') ELSE (\n  SET "_prog=node"\n)\n'
                'endLocal & goto #_undefined_# 2>NUL || title %COMSPEC% & '
                '"%_prog%"  "%dp0%\\node_modules\\@jackwener\\opencli\\dist\\main.js" %*\n',
                encoding="utf-8",
            )
            self.assertEqual(xhs.resolve_windows_opencli_shim(shim), [str(node), str(script)])

    def test_npm_cmd_shim_falls_back_to_node_on_path(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            script = base / "node_modules" / "opencli" / "main.js"
            script.parent.mkdir(parents=True)
            script.touch()
            shim = base / "opencli.cmd"
            shim.write_text(
                '"%_prog%"  "%~dp0\\node_modules\\opencli\\main.js" %*\n',
                encoding="utf-8",
            )
            with patch.object(xhs.shutil, "which", return_value="node-on-path"):
                self.assertEqual(
                    xhs.resolve_windows_opencli_shim(shim), ["node-on-path", str(script)]
                )

    def test_unknown_wrapper_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            shim = Path(folder) / "opencli.cmd"
            shim.write_text("@echo off\nopencli %*\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "WRAPPER_UNSAFE_OR_UNKNOWN"):
                xhs.resolve_windows_opencli_shim(shim)

    def test_signed_urls_stay_as_single_argument_without_shell(self):
        url = "https://www.xiaohongshu.com/search_result?xsec_token=a&xsec_source=pc%25"
        with patch.object(xhs.subprocess, "run") as call:
            call.return_value.returncode = 0
            call.return_value.stdout = "ok"
            self.assertEqual(xhs.run_cli(["node", "main.js"], ["browser", "open", url], 10), (0, "ok"))
            args, kwargs = call.call_args
            self.assertEqual(args[0], ["node", "main.js", "browser", "open", url])
            self.assertIs(kwargs["shell"], False)


if __name__=="__main__":
    unittest.main()
