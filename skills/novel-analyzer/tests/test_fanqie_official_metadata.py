"""A corrupted rank glyph is never guessed; official detail URL is verified."""
import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


DETAIL = load("fanqie_detail_metadata")
RANK = load("fanqie_refresh")
DECODER = load("fanqie_decoder")


class Page:
    def __init__(self, address, result):
        self.url = address
        self.result = result
        self.closed = False

    def goto(self, url, *, wait_until, timeout):
        self.url = self.url if self.url else url

    def evaluate(self, js):
        return self.result

    def close(self):
        self.closed = True


class Browser:
    def __init__(self, page):
        self.context = self
        self.page = page

    def new_page(self):
        return self.page


class FirstPartyMetadataTests(unittest.TestCase):
    def test_real_url_only_and_exact_book_id(self):
        with self.assertRaisesRegex(ValueError, "INVALID_BOOK_ID"):
            DETAIL.detail_metadata(Browser(None), "/page/../other")
        with self.assertRaisesRegex(ValueError, "INVALID_BOOK_ID"):
            DETAIL.detail_metadata(Browser(None), "https://evil.example/page/123456789")

    def test_first_party_unicode_title_is_evidence_linked(self):
        url = "https://fanqienovel.com/page/7077516958534470656"
        page = Page(url, {
            "heading": "凡骨",
            "title": "凡骨完整版在线免费阅读_番茄小说官网",
            "description": "官方简介",
        })
        got = DETAIL.detail_metadata(Browser(page), "/page/7077516958534470656")
        self.assertEqual(got["title"], "凡骨")
        self.assertEqual(got["evidence_url"], url)
        self.assertTrue(page.closed)

    def test_redirect_or_obfuscated_detail_is_refused(self):
        path = "/page/7077516958534470656"
        for url, heading, title in (
            ("https://other.example/page/7077516958534470656", "凡骨", "凡骨"),
            ("https://fanqienovel.com/page/888888888888", "凡骨", "凡骨"),
            ("https://fanqienovel.com" + path, "\ue4b5", "\ue4b5"),
        ):
            page = Page(url, {"heading": heading, "title": title})
            with self.assertRaises(ValueError):
                DETAIL.detail_metadata(Browser(page), path)

    def test_unreadable_rank_author_uses_verified_detail_without_guessing(self):
        href = "/page/7077516958534470656"
        book = {
            "title": "凡骨", "author": "作者\ue4b5", "intro": "剧情\ue4c2",
            "reads": "123万在读", "url": href,
        }
        called = []

        def resolver(url):
            called.append(url)
            return {
                "title": "凡骨",
                "description": "官方作品简介",
                "evidence_url": "https://fanqienovel.com" + href,
            }

        books = RANK.normalize_books([book], DECODER.decode_text, 6, detail_resolver=resolver)
        self.assertEqual(called, [href])
        self.assertEqual(len(books), 1)
        self.assertEqual(books[0]["title"], "凡骨")
        self.assertEqual(books[0]["author"], "未知")
        self.assertEqual(books[0]["intro"], "官方作品简介")
        self.assertEqual(books[0]["reads"], "123万")
        self.assertEqual(set(books[0]["unreadable_rank_fields"]), {"author", "intro"})

    def test_no_detail_source_never_passes_obfuscated_field(self):
        with self.assertRaisesRegex(ValueError, "NEEDS_VERIFIED_OFFICIAL_DETAIL"):
            RANK.normalize_books([{"title": "书名\ue4b5"}], DECODER.decode_text, 1)


if __name__ == "__main__":
    unittest.main()
