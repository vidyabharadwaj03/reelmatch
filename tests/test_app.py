import base64
import subprocess
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from app import media, server
from app.planner import make_plan
from app.script import make_scripts, word_budget
from app.registry import apply_override, choose

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


class ChooserTests(unittest.TestCase):
    def test_many_photos_long_video_with_sound_picks_seedance(self):
        self.assertEqual(choose({"duration": 15}, 5)["model"], "seedance-2.5-draft")

    def test_single_photo_short_product_picks_a_cheap_tested_model(self):
        r = choose({"duration": 5, "needs_audio": False, "subject": "product"}, 1)
        best = next(x for x in r["ranking"] if x["id"] == r["model"])
        self.assertEqual(best["status"], "verified")
        self.assertLessEqual(r["cost"], 50)
        self.assertNotEqual(r["model"], "seedance-2.5-draft")
        for other in ("grok-imagine-1.5-lite", "wan-2.7-i2v"):
            self.assertTrue(next(x for x in r["ranking"] if x["id"] == other)["eligible"], other)
    def test_sound_requirement_rules_out_wan(self):
        r = choose({"duration": 5}, 1)
        wan = next(x for x in r["ranking"] if x["id"] == "wan-2.7-i2v")
        self.assertFalse(wan["eligible"])
        self.assertTrue(any("No generated sound" in c["text"] for c in wan["checks"]))
    def test_long_video_only_seedance_fits(self):
        self.assertEqual(choose({"duration": 25}, 3)["model"], "seedance-2.5-draft")

    def test_verified_likeness_routes_to_the_verified_person_model(self):
        r = choose({"duration": 15, "verified_likeness": True}, 2)
        self.assertEqual(r["model"], "seedance-2.0-real-human")
        plain = next(x for x in r["ranking"] if x["id"] == "seedance-2.5-draft")
        self.assertFalse(plain["eligible"])

    def test_the_verified_person_model_is_never_used_without_a_verified_person(self):
        r = choose({"duration": 15}, 5)
        kyc = next(x for x in r["ranking"] if x["id"] == "seedance-2.0-real-human")
        self.assertFalse(kyc["eligible"])
        self.assertTrue(any("verified person" in c["text"] for c in kyc["checks"]))
    def test_budget_too_small_means_no_model(self):
        self.assertIsNone(choose({"duration": 5, "budget": 2}, 1)["model"])
    def test_models_without_an_adapter_are_never_eligible(self):
        for r in choose({"duration": 15}, 5)["ranking"]:
            if not r["checks"][0]["ok"]:  # first check is "adapter wired up"
                self.assertFalse(r["eligible"], r["id"])
    def test_untested_models_are_never_picked_while_a_tested_one_fits(self):
        # Regression: cheap untested models (HeyGen, Pruna) used to outrank Seedance on price alone.
        for brief, n in (({"duration": 15}, 5), ({"duration": 10, "subject": "product"}, 3), ({"duration": 5, "subject": "product"}, 1)):
            r = choose(brief, n)
            self.assertEqual(next(x for x in r["ranking"] if x["id"] == r["model"])["status"], "verified", (brief, r["model"]))

    def test_an_untested_model_can_still_be_chosen_by_hand(self):
        r = apply_override(choose({"duration": 5, "subject": "product"}, 1), "pruna-p-video-2")
        self.assertEqual(r["model"], "pruna-p-video-2")
        self.assertTrue(r["overridden"])

    def test_untested_model_is_picked_only_when_nothing_tested_fits(self):
        r = choose({"duration": 20, "n_videos": 0, "subject": "product", "needs_audio": True}, 10)  # 10 photos: only keyframe models
        best = next(x for x in r["ranking"] if x["id"] == r["model"])
        self.assertTrue(best["eligible"])

    def test_every_model_explains_itself(self):
        for r in choose({"duration": 15}, 5)["ranking"]:
            self.assertTrue(r["checks"])


class SubjectTests(unittest.TestCase):
    def test_product_ads_skip_likeness_checks(self):
        r = choose({"duration": 8, "subject": "product"}, 3)
        best = r["ranking"][0]
        self.assertEqual(r["model"], "seedance-2.5-draft")
        self.assertTrue(any("likeness rules do not apply" in c["text"] for c in best["checks"]))

    def test_people_ads_flag_models_untested_with_real_faces(self):
        wan = next(r for r in choose({"duration": 5, "subject": "people", "needs_audio": False}, 1)["ranking"] if r["id"] == "wan-2.7-i2v")
        self.assertTrue(any("Not tested with real-person" in c["text"] for c in wan["checks"]))

    def test_models_we_ran_are_not_flagged_as_untested_with_real_faces(self):
        r = choose({"duration": 5, "subject": "people", "needs_audio": False}, 1)
        for x in r["ranking"]:
            if x["status"] == "verified" and x["id"] != "wan-2.7-i2v":
                self.assertFalse(any("Not tested with real-person" in c["text"] for c in x["checks"]), x["id"])
    def test_open_weights_only_picks_only_open_weights_models(self):
        r = choose({"duration": 15, "subject": "product", "open_weights_only": True}, 3)
        self.assertIn(r["model"], ("minimax-h3-r2v", "ltx-2.5-i2v"))
        for x in r["ranking"]:
            if x["eligible"]:
                self.assertEqual(x["open_weights"], "yes", x["id"])
    def test_every_listed_model_has_evidence(self):
        for r in choose({"duration": 15}, 3)["ranking"]:
            self.assertTrue(r["evidence"], r["id"])

    def test_blog_evidence_always_has_a_source_link_or_is_ran_comfy(self):
        for r in choose({"duration": 15}, 3)["ranking"]:
            for e in r["evidence"]:
                if e["kind"] == "blog":
                    self.assertTrue(e["url"], r["id"])


class AdapterGraphTests(unittest.TestCase):
    PROMPT = "Vertical ad. Shot 1: friends with a sign. Draw on reference photo 1. Shot 2: laugh. Draw on reference photo 2."

    def _g(self, key, n=3, d=8):
        from app import adapters
        return adapters.BUILDERS[key][1](self.PROMPT, [f"p{i}.jpg" for i in range(n)], d)

    def test_every_partner_builder_makes_one_partner_node_and_a_save_node(self):
        from app import adapters
        for key in ("grok", "pruna", "flux3", "kling4", "heygen", "veo"):
            g = self._g(key)
            self.assertEqual(g["776"]["class_type"], "SaveVideo", key)
            self.assertEqual(g["776"]["inputs"]["video"], ["789", 0], key)
            self.assertIn(g["789"]["class_type"], {"GrokVideoNode", "PrunaImageToVideoNode", "Flux3MaxImageToVideoNode", "Kling4ImageToVideoNode",
                                                    "HeyGenReferenceToVideoNode", "Veo3VideoGenerationNode"})

    def test_ltx_graph_gets_the_photo_prompt_length_and_portrait_shape(self):
        g = self._g("ltx25", n=1, d=8)
        self.assertEqual(g["395"]["inputs"]["image"], "p0.jpg")
        self.assertEqual(g["398:362"]["inputs"]["value"], 8)
        self.assertIn("Portrait", g["403"]["inputs"]["aspect_ratio"])
        self.assertTrue(g["398:376"]["inputs"]["value"].startswith("Use the provided start image as the first frame."))
        self.assertIn("SaveVideo", {v["class_type"] for v in g.values()})

    def test_h3_graph_turns_photos_into_picture_references_and_cuts(self):
        g = self._g("h3", n=3, d=6)
        refs = sorted(k for k in g["136"]["inputs"] if k.startswith("ref_images."))
        self.assertEqual(refs, ["ref_images.ref_image_0", "ref_images.ref_image_1", "ref_images.ref_image_2"])
        text = g["138"]["inputs"]["value"]
        self.assertIn("<Picture 1>", text)
        self.assertIn("CUT 1:", text)
        self.assertNotIn("reference photo", text)
        self.assertEqual(g["132"]["inputs"]["value"], 6)

    def test_h3_with_one_photo_drops_the_second_reference_slot(self):
        g = self._g("h3", n=1)
        self.assertNotIn("139", g)
        self.assertEqual([k for k in g["136"]["inputs"] if k.startswith("ref_images.")], ["ref_images.ref_image_0"])

    def test_saved_open_weights_graphs_have_every_node_the_builders_edit(self):
        for key, ids in (("ltx25", ("395", "398:376", "398:362", "403", "75")), ("h3", ("136", "137", "138", "132", "115", "92"))):
            g = self._g(key, n=2)
            for nid in ids:
                self.assertIn(nid, g, (key, nid))
    def test_single_image_models_use_only_the_first_photo(self):
        for key in ("grok", "veo"):
            g = self._g(key)
            self.assertEqual(sum(1 for v in g.values() if v["class_type"] == "LoadImage"), 1, key)

    def test_flux_spreads_photos_as_keyframes(self):
        n = self._g("flux3", n=4)["789"]["inputs"]
        self.assertEqual([k for k in n if k.startswith("keyframes.")], [f"keyframes.image_{i}" for i in range(4)])
        self.assertEqual(n["duration"], "8")  # this node wants the length as text

    def test_kling_uses_first_middle_and_last_frames_and_caps_at_ten(self):
        n = self._g("kling4", n=4)["789"]["inputs"]
        self.assertEqual(n["model.first_frame"], ["900", 0])
        self.assertEqual(n["model.last_frame"], ["903", 0])
        self.assertEqual({k for k in n if "middle_frame" in k}, {"model.middle_frames.middle_frame_1", "model.middle_frames.middle_frame_2"})
        big = self._g("kling4", n=14)
        self.assertEqual(sum(1 for v in big.values() if v["class_type"] == "LoadImage"), 10)

    def test_heygen_and_kling_refer_to_photos_as_at_image(self):
        for key in ("heygen", "kling4"):
            text = self._g(key)["789"]["inputs"]["model.prompt"]
            self.assertIn("@Image1", text, key)
            self.assertNotIn("reference photo", text, key)

    def test_veo_only_renders_four_six_or_eight_seconds(self):
        from app import adapters
        self.assertEqual([adapters.veo_seconds(d) for d in (3, 5, 7, 8, 15)], [4, 4, 6, 8, 8])

    def test_prompts_are_cut_to_each_models_limit_at_a_word(self):
        from app import adapters
        long = "word " * 600
        self.assertLessEqual(len(adapters.short(long, 800)), 801)
        self.assertTrue(adapters.short(long, 800).endswith("word."))

    def test_vertical_crop_makes_a_9_by_16_photo(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            src, out = d / "wide.jpg", d / "tall.jpg"
            subprocess.run([media.ffmpeg_exe(), "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=800x600:rate=1", "-frames:v", "1", str(src)], check=True)
            media.crop_vertical(src, out)
            w, h = media.video_size(out)
            self.assertAlmostEqual(w / h, 9 / 16, delta=0.02)


class PickTests(unittest.TestCase):
    def test_soraa_style_ad_stays_on_the_model_tested_that_far(self):
        self.assertEqual(choose({"duration": 15}, 5)["model"], "seedance-2.5-draft")

    def test_photos_that_would_be_ignored_cost_a_model_the_pick(self):
        # Regression: LTX (one photo) used to win a 20s, five-photo ad on price alone.
        for brief, n in (({"duration": 20}, 5), ({"duration": 30, "subject": "product"}, 3)):
            r = choose(brief, n)
            self.assertEqual(r["model"], "seedance-2.5-draft", brief)

    def test_two_photo_short_ad_goes_to_open_weights_h3(self):
        self.assertEqual(choose({"duration": 5}, 2)["model"], "minimax-h3-r2v")

    def test_models_never_claim_inputs_their_adapter_does_not_send(self):
        # Regression: HeyGen and H3 listed reference video support their adapters did not use.
        for m in __import__("app.registry", fromlist=["MODELS"]).MODELS:
            if m.adapter in ("grok", "pruna", "flux3", "kling4", "heygen", "veo", "ltx25", "h3", "wan"):
                self.assertEqual((m.video_refs, m.audio_refs), (0, 0), m.id)


class LikenessTests(unittest.TestCase):
    def setUp(self):
        from app import likeness
        self._tmp = tempfile.TemporaryDirectory()
        self.likeness = likeness
        self._patch = mock.patch.object(likeness, "STORE", Path(self._tmp.name) / "likeness.json")
        self._patch.start()
        likeness._save_people([{"id": "p1", "name": "Vidya", "group_id": "SECRET-GROUP", "asset_ids": ["SECRET-ASSET"], "created": 1},
                               {"id": "p2", "name": "Sam", "group_id": "g2", "asset_ids": ["a2"], "created": 2}])

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def test_the_page_never_sees_the_verification_ids(self):
        shown = str(self.likeness.public_people())
        self.assertIn("Vidya", shown)
        self.assertNotIn("SECRET", shown)

    def test_selected_people_resolve_in_order_and_unknown_ids_are_dropped(self):
        self.assertEqual([p["name"] for p in self.likeness.resolve(["p2", "nope", "p1"])], ["Sam", "Vidya"])

    def test_deleting_a_person_removes_them(self):
        self.assertTrue(self.likeness.delete_person("p1"))
        self.assertEqual([p["id"] for p in self.likeness.public_people()], ["p2"])
        self.assertFalse(self.likeness.delete_person("p1"))

    def test_the_store_is_readable_only_by_the_owner(self):
        self.assertEqual(oct(self.likeness.STORE.stat().st_mode & 0o777), "0o600")

    def test_the_verification_link_is_found_but_download_links_are_not_mistaken_for_it(self):
        f = self.likeness.find_link
        self.assertEqual(f("Open https://verify.example.com/h5?token=abc to continue."), "https://verify.example.com/h5?token=abc")
        self.assertIsNone(f("saved to https://storage.googleapis.com/comfy-cloud-assets/x.mp4?sig=1"))
        self.assertIsNone(f("no link here"))

    def test_the_verification_graph_runs_the_liveness_flow_with_an_empty_group(self):
        g = self.likeness.verification_graph("me.jpg")
        self.assertEqual(g["2"]["class_type"], "ByteDanceCreateImageAsset")
        self.assertEqual(g["2"]["inputs"]["group_id"], "")
        self.assertEqual((g["3"]["inputs"]["text"], g["4"]["inputs"]["text"]), (["2", 0], ["2", 1]))

    def test_selecting_a_person_sets_the_flag_names_and_asset_ids(self):
        brief = server.clean_brief({"duration": 8, "people": ["p1", "bogus"]})
        assets = server.apply_people(brief)
        self.assertEqual(assets, ["SECRET-ASSET"])
        self.assertEqual(brief["people_names"], ["Vidya"])
        self.assertTrue(brief["verified_likeness"])
        self.assertEqual(choose(brief, 0)["model"], "seedance-2.0-real-human")

    def test_product_ads_ignore_selected_people(self):
        brief = server.clean_brief({"duration": 8, "subject": "product", "people": ["p1"]})
        self.assertEqual(brief["people"], [])
        self.assertEqual(server.apply_people(brief), [])
        self.assertFalse(brief["verified_likeness"])

    def test_the_plan_refers_to_each_person_by_asset_number(self):
        from app.planner import make_plan
        plan = make_plan({"duration": 8, "people_names": ["Vidya", "Sam"]}, 1)
        self.assertIn("@asset_1", plan)
        self.assertIn("Vidya", plan)
        self.assertIn("@asset_2", plan)

    def test_the_seedance_graph_carries_asset_ids_as_plain_strings(self):
        from app.pipeline import build_seedance_graph
        n = build_seedance_graph("p", [], 5, assets=["A1", "A2"])["789"]["inputs"]
        self.assertEqual((n["model.reference_assets.asset_1"], n["model.reference_assets.asset_2"]), ("A1", "A2"))
        self.assertFalse([k for k in n if "reference_images" in k])

    def test_starting_a_check_needs_consent_a_name_and_live_mode(self):
        h = server.Handler
        with mock.patch.object(server.pipeline, "MOCK", False), mock.patch.object(server.pipeline, "key_present", return_value=True):
            with self.assertRaises(server.BadRequest):
                h._likeness_start(None, {"name": "", "consent": True})
            with self.assertRaises(server.BadRequest):
                h._likeness_start(None, {"name": "Vidya", "consent": False})
        with mock.patch.object(server.pipeline, "MOCK", True):
            with self.assertRaises(server.BadRequest) as cm:
                h._likeness_start(None, {"name": "Vidya", "consent": True})
            self.assertIn("live mode", str(cm.exception))


class TestedRangeTests(unittest.TestCase):
    def test_a_model_tested_on_one_photo_does_not_win_a_five_photo_ad(self):
        r = choose({"duration": 15, "subject": "people"}, 5)
        self.assertEqual(r["model"], "seedance-2.5-draft")
        heygen = next(x for x in r["ranking"] if x["id"] == "heygen-video-1-r2v")
        self.assertTrue(heygen["eligible"])
        self.assertTrue(any("Only tested with up to 1 photo" in c["text"] for c in heygen["checks"]))

    def test_longer_than_tested_is_flagged(self):
        r = choose({"duration": 12, "subject": "product"}, 1)
        grok = next(x for x in r["ranking"] if x["id"] == "grok-imagine-1.5-lite")
        self.assertTrue(any("Only tested up to 5s" in c["text"] for c in grok["checks"]))

    def test_all_wired_models_have_a_price_and_a_range(self):
        from app.registry import MODELS
        for m in MODELS:
            if m.adapter:
                self.assertIsNotNone(m.cost(m.min_s or 5), m.id)

    def test_every_adapter_key_has_a_runner(self):
        from app import pipeline
        from app.registry import MODELS
        for m in MODELS:
            if m.adapter:
                self.assertIn(m.adapter, pipeline.ADAPTERS, m.id)


class MediaInputTests(unittest.TestCase):
    def test_reference_video_rules_out_models_that_cannot_take_it(self):
        r = choose({"duration": 5, "subject": "product", "n_videos": 1}, 1)
        self.assertEqual(r["model"], "seedance-2.5-draft")
        wan = next(x for x in r["ranking"] if x["id"] == "wan-2.7-i2v")
        self.assertFalse(wan["eligible"])
        self.assertTrue(any("Cannot take a reference video" in c["text"] for c in wan["checks"]))

    def test_music_is_mixed_in_so_silent_models_still_fit(self):
        r = choose({"duration": 5, "subject": "product", "n_audio": 1, "soundtrack": True}, 1)
        wan = next(x for x in r["ranking"] if x["id"] == "wan-2.7-i2v")
        self.assertTrue(wan["eligible"])

    def test_without_mixing_a_silent_model_is_out_again(self):
        r = choose({"duration": 5, "subject": "product", "n_audio": 1, "soundtrack": False}, 1)
        wan = next(x for x in r["ranking"] if x["id"] == "wan-2.7-i2v")
        self.assertFalse(wan["eligible"])

    def test_seedance_graph_gets_media_nodes_only_when_media_is_given(self):
        from app.pipeline import build_seedance_graph
        plain = build_seedance_graph("p", ["a.jpg"], 8)["789"]["inputs"]
        self.assertEqual(plain["model.task_type"], "auto")
        self.assertFalse([k for k in plain if "reference_videos" in k or "reference_audios" in k])
        full = build_seedance_graph("p", ["a.jpg"], 8, ["v.mp4"], ["m.mp3"])
        self.assertEqual(full["789"]["inputs"]["model.task_type"], "reference")
        self.assertEqual(full["801"]["class_type"], "LoadVideo")
        self.assertEqual(full["821"]["class_type"], "LoadAudio")

    def test_sniffers(self):
        self.assertTrue(media.sniff_video(b"\x00\x00\x00\x18ftypmp42"))
        self.assertTrue(media.sniff_audio(b"ID3\x03\x00"))
        self.assertTrue(media.sniff_audio(b"RIFF\x00\x00\x00\x00WAVEfmt "))
        self.assertFalse(media.sniff_video(b"<html>nope</html>"))
        self.assertFalse(media.sniff_audio(b"MZ not audio at all"))

    def test_upload_rejects_fake_video_and_wrong_type(self):
        fake = base64.b64encode(b"this is plain text pretending").decode()
        with self.assertRaises(server.BadRequest):
            server.save_media([{"name": "x.mp4", "data": fake}], "video")
        with self.assertRaises(server.BadRequest):
            server.save_media([{"name": "x.avi", "data": fake}], "video")
        with self.assertRaises(server.BadRequest):
            server.save_media([{"name": "x.mp3", "data": fake}], "audio")

    def test_mixing_replaces_the_sound_and_keeps_the_length(self):
        ff = media.ffmpeg_exe()
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            v, a, out = d / "v.mp4", d / "a.wav", d / "out.mp4"
            subprocess.run([ff, "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=160x284:rate=24", "-f", "lavfi", "-i",
                            "anullsrc=r=44100:cl=mono", "-t", "3", "-pix_fmt", "yuv420p", "-shortest", str(v)], check=True)
            subprocess.run([ff, "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(a)], check=True)
            media.mux_soundtrack(v, a, out)  # 1s track looped under a 3s video
            self.assertAlmostEqual(media.duration_seconds(out), media.duration_seconds(v), delta=0.15)
            banner = subprocess.run([ff, "-hide_banner", "-i", str(out)], capture_output=True, text=True).stderr
            self.assertIn("Audio:", banner)
            self.assertIn("Video:", banner)


def _clips(d: Path):
    """Tiny synthetic media: an 8s clip with sound, an 8s silent clip, a 1s music loop and a 2s voice."""
    ff = media.ffmpeg_exe()
    run = lambda *a: subprocess.run([ff, "-loglevel", "error", "-y", *a], check=True)
    run("-f", "lavfi", "-i", "testsrc=size=160x284:rate=24", "-f", "lavfi", "-i", "sine=frequency=300:duration=8", "-t", "8", "-pix_fmt", "yuv420p", "-shortest", str(d / "sound.mp4"))
    run("-f", "lavfi", "-i", "testsrc2=size=320x568:rate=30", "-t", "8", "-pix_fmt", "yuv420p", str(d / "silent.mp4"))
    run("-f", "lavfi", "-i", "sine=frequency=500:duration=1", str(d / "music.wav"))
    run("-f", "lavfi", "-i", "sine=frequency=900:duration=2", str(d / "voice.wav"))


class AudioMixTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        _clips(self.d)

    def tearDown(self):
        self._tmp.cleanup()

    def _assert_full_audio(self, out, video):
        self.assertAlmostEqual(media.audio_seconds(out), media.duration_seconds(video), delta=0.3)

    def test_music_keeps_playing_after_a_short_voice_ends(self):
        # Regression: the ducking filter used to end with the voice and cut the music off at 2.4s.
        out = self.d / "o.mp4"
        media.mix_audio(self.d / "sound.mp4", out, music=self.d / "music.wav", voice=self.d / "voice.wav")
        self._assert_full_audio(out, self.d / "sound.mp4")

    def test_music_only_spans_the_whole_video(self):
        out = self.d / "o.mp4"
        media.mix_audio(self.d / "silent.mp4", out, music=self.d / "music.wav")
        self._assert_full_audio(out, self.d / "silent.mp4")

    def test_voice_over_the_videos_own_sound_spans_the_whole_video(self):
        out = self.d / "o.mp4"
        media.mix_audio(self.d / "sound.mp4", out, voice=self.d / "voice.wav")
        self._assert_full_audio(out, self.d / "sound.mp4")

    def test_voice_over_a_silent_video_spans_the_whole_video(self):
        out = self.d / "o.mp4"
        media.mix_audio(self.d / "silent.mp4", out, voice=self.d / "voice.wav")
        self._assert_full_audio(out, self.d / "silent.mp4")

    def test_mix_needs_something_to_mix(self):
        with self.assertRaises(ValueError):
            media.mix_audio(self.d / "sound.mp4", self.d / "o.mp4")

    def test_joining_a_silent_and_a_sound_clip_keeps_sound_and_length(self):
        out = self.d / "joined.mp4"
        media.concat_clips(self.d / "silent.mp4", self.d / "sound.mp4", out, size_from=self.d / "sound.mp4")
        self.assertAlmostEqual(media.duration_seconds(out), 16.0, delta=0.2)
        self.assertEqual(media.video_size(out), (160, 284))
        self.assertAlmostEqual(media.audio_seconds(out), 16.0, delta=0.3)

    def test_trim_cuts_long_clips_and_leaves_short_ones(self):
        cut = media.trim(self.d / "sound.mp4", self.d / "cut.mp4", 3.0)
        self.assertLess(media.duration_seconds(cut), 4.2)
        self.assertEqual(media.trim(self.d / "sound.mp4", self.d / "x.mp4", 15.0), self.d / "sound.mp4")


class ScriptTests(unittest.TestCase):
    BRIEF = {"brand": "Soraa", "description": "A new way to find brand partnerships. Second sentence.", "message": "You'd stop scrolling for us.",
             "cta": "follow", "audience": "genz", "goal": "awareness"}

    def test_every_script_fits_the_ad_length(self):
        for d in (5, 8, 15, 30):
            r = make_scripts({**self.BRIEF, "duration": d})
            self.assertEqual(r["budget_words"], word_budget(d))
            for s in r["scripts"]:
                self.assertLessEqual(s["words"], r["budget_words"] + 2, (d, s["title"]))

    def test_scripts_keep_the_message_and_call_to_action(self):
        for s in make_scripts({**self.BRIEF, "duration": 15})["scripts"]:
            self.assertIn("stop scrolling", s["text"])
            self.assertIn("Follow us", s["text"])

    def test_scripts_work_with_a_nearly_empty_brief(self):
        r = make_scripts({"duration": 8})
        self.assertEqual(len(r["scripts"]), 3)
        self.assertTrue(all(s["text"].strip() for s in r["scripts"]))

    def test_longer_ads_get_bigger_word_budgets(self):
        self.assertLess(word_budget(8), word_budget(15))
        self.assertLess(word_budget(15), word_budget(30))


class ExtendEditTests(unittest.TestCase):
    def test_only_seedance_can_extend_or_edit(self):
        for mode in ("extend_forward", "extend_backward", "edit"):
            r = choose({"duration": 8, "n_videos": 1, "video_mode": mode}, 0)
            self.assertEqual(r["model"], "seedance-2.5-draft", mode)
            for x in r["ranking"]:
                if x["id"] != "seedance-2.5-draft":
                    self.assertFalse(x["eligible"], (mode, x["id"]))

    def test_extend_plan_says_which_way(self):
        fwd = make_plan({"duration": 8, "n_videos": 1, "video_mode": "extend_forward", "description": "they walk in"}, 0)
        back = make_plan({"duration": 8, "n_videos": 1, "video_mode": "extend_backward"}, 0)
        self.assertIn("forward", fwd)
        self.assertIn("they walk in", fwd)
        self.assertIn("backward", back)

    def test_edit_plan_keeps_timing_and_states_the_change(self):
        plan = make_plan({"duration": 8, "n_videos": 1, "video_mode": "edit", "description": "make it rain"}, 0)
        self.assertIn("original timing", plan)
        self.assertIn("make it rain", plan)

    def test_without_a_video_the_normal_plan_is_used(self):
        self.assertIn("Shot 1", make_plan({"duration": 8, "video_mode": "extend_forward"}, 2))

    def test_voiceover_counts_as_sound_so_silent_models_still_fit(self):
        r = choose({"duration": 5, "subject": "product", "n_voice": 1, "needs_audio": True}, 1)
        wan = next(x for x in r["ranking"] if x["id"] == "wan-2.7-i2v")
        self.assertTrue(wan["eligible"])

    def test_video_mode_falls_back_to_reference(self):
        self.assertEqual(server.clean_brief({"duration": 8, "video_mode": "nonsense"})["video_mode"], "reference")


class OverrideTests(unittest.TestCase):
    def test_auto_pick_is_remembered(self):
        r = choose({"duration": 5, "subject": "product", "needs_audio": False}, 1)
        self.assertEqual(r["auto_model"], r["model"])
        self.assertFalse(r["overridden"])

    def test_user_can_switch_to_another_model_that_fits(self):
        r = choose({"duration": 5, "subject": "product", "needs_audio": False}, 1)
        auto = r["model"]
        self.assertNotEqual(auto, "seedance-2.5-draft")
        other = apply_override(r, "seedance-2.5-draft")
        self.assertEqual(other["model"], "seedance-2.5-draft")
        self.assertTrue(other["overridden"])
        self.assertEqual(other["cost"], 156)
        self.assertEqual(other["auto_model"], auto)
    def test_a_model_that_cannot_do_the_job_is_refused_with_a_reason(self):
        r = choose({"duration": 15, "subject": "people"}, 5)
        with self.assertRaises(ValueError) as cm:
            apply_override(r, "wan-2.7-i2v")
        self.assertIn("Wan 2.7", str(cm.exception))

    def test_unwired_models_cannot_be_picked(self):
        r = choose({"duration": 15}, 3)
        with self.assertRaises(ValueError):
            apply_override(r, "veo-3.1")

    def test_unknown_or_empty_override_changes_nothing(self):
        r = choose({"duration": 15}, 3)
        self.assertIs(apply_override(r, None), r)
        with self.assertRaises(ValueError):
            apply_override(r, "nope")

    def test_quote_answers_from_counts_alone(self):
        q = server.Handler._quote(None, {"brief": {"duration": 8, "subject": "product"}, "counts": {"images": 3}})
        self.assertEqual(q["model"]["model"], "seedance-2.5-draft")
        self.assertEqual(q["credits"], 250)

    def test_quote_ignores_a_stale_override(self):
        q = server.Handler._quote(None, {"brief": {"duration": 15}, "counts": {"images": 5}, "model_id": "wan-2.7-i2v"})
        self.assertTrue(q["override_ignored"])
        self.assertEqual(q["model"]["model"], "seedance-2.5-draft")

    def test_quote_edit_uses_the_source_clip_length(self):
        q = server.Handler._quote(None, {"brief": {"duration": 15, "video_mode": "edit"}, "counts": {"videos": 1}, "video_seconds": 6.2})
        self.assertEqual(q["duration"], 7)


class LiveAdapterTests(unittest.TestCase):
    def test_seedance_sends_the_api_key_with_the_job(self):
        # Regression: without api_key, Comfy rejects the partner-model step with "Unauthorized: Please login first".
        from app import pipeline

        calls = {}

        class FakeOut:
            content_type, name = "video/mp4", "x.mp4"

            def to_file(self, path):
                Path(path).write_bytes(b"x")

        class FakeJob:
            outputs = [FakeOut()]

        class FakeClient:
            workflows = mock.Mock()

            def run(self, wf, **kw):
                calls.update(kw)
                return FakeJob()

        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"COMFY_API_KEY": "test-key"}), \
                mock.patch("comfy_sdk.Comfy", return_value=FakeClient()), mock.patch.object(pipeline, "upload_file", return_value="a.jpg"), \
                mock.patch.object(pipeline, "_set"):
            pipeline._seedance("job", "prompt", [Path("a.jpg")], 5, Path(d) / "out.mp4")
        self.assertEqual(calls.get("api_key"), "test-key")

    def test_a_failed_render_shows_comfys_reason_not_a_generic_message(self):
        from app.pipeline import friendly_error

        class JobFailed(Exception):
            pass

        err = JobFailed("job abc ended failed")
        err.error = mock.Mock(message="Unauthorized: Please login first to use this node.")
        self.assertIn("API key", friendly_error(err))
        err.error = mock.Mock(message="Prompt was too long")
        self.assertIn("Prompt was too long", friendly_error(err))


class BlankStartTests(unittest.TestCase):
    def test_no_photos_means_no_photos(self):
        self.assertEqual(server.gather_images({"folder": "", "uploads": []}), [])
        self.assertEqual(server.gather_images({}), [])

    def test_added_photos_win_over_a_folder(self):
        from app import pipeline
        png = base64.b64encode(PNG).decode()
        got = server.gather_images({"folder": "assets/soraa", "uploads": [{"name": "mine.png", "data": png}]})
        self.assertEqual([p.name for p in got], ["mine.png"])

    def test_a_missing_folder_is_just_empty(self):
        self.assertEqual(server.folder_images("/definitely/not/a/real/folder"), [])


class PlannerTests(unittest.TestCase):
    def test_one_shot_per_beat_and_end_card(self):
        plan = make_plan({"brand": "Soraa", "duration": 15, "message": "Stop scrolling."}, 5)
        self.assertEqual(plan.count("Shot "), 5)
        self.assertIn("end card", plan)
        self.assertNotIn('."."', plan)
        self.assertNotIn("..", plan)

    def test_product_plan_has_no_people_and_keeps_label(self):
        plan = make_plan({"brand": "Oud", "subject": "product", "duration": 8}, 2)
        self.assertIn("No people on screen", plan)
        self.assertIn("label", plan)

    def test_chips_flow_into_the_plan(self):
        plan = make_plan({"duration": 8, "style": ["luxury"], "camera": ["orbit"], "setting": "studio", "cta": "shop"}, 1)
        for text in ("elegant", "orbit", "studio backdrop", "Shop now"):
            self.assertIn(text, plan)

    def test_photos_are_referenced_in_rotation(self):
        plan = make_plan({"duration": 15}, 2)
        self.assertIn("reference photo 1", plan)
        self.assertIn("reference photo 2", plan)

    def test_no_photo_reference_without_photos(self):
        self.assertNotIn("Draw on reference photo", make_plan({"duration": 8}, 0))


class ValidationTests(unittest.TestCase):
    def test_brief_rejects_bad_length(self):
        for bad in (3, 31, "abc"):
            with self.assertRaises(server.BadRequest):
                server.clean_brief({"duration": bad})

    def test_brief_defaults_and_trims(self):
        b = server.clean_brief({"duration": "15", "goal": "nonsense", "brand": "  X  ", "budget": ""})
        self.assertEqual((b["goal"], b["brand"], b["budget"]), ("awareness", "X", None))
        self.assertTrue(b["needs_audio"])

    def test_unknown_option_values_fall_back(self):
        b = server.clean_brief({"duration": 8, "subject": "x", "setting": "x", "style": ["luxury", "nope"], "cta": "x"})
        self.assertEqual((b["subject"], b["setting"], b["style"], b["cta"]), ("people", "street_night", ["luxury"], "none"))

    def test_verified_likeness_is_dropped_for_product_ads(self):
        self.assertFalse(server.clean_brief({"duration": 8, "subject": "product", "verified_likeness": True})["verified_likeness"])

    def test_options_cover_every_chip_the_page_uses(self):
        from app import options
        for group in ("subject", "goal", "platform", "length", "style", "setting", "camera", "audio", "budget", "audience", "cta"):
            self.assertTrue(options.values(group), group)

    def test_sniff_accepts_real_images_only(self):
        self.assertTrue(server.sniff_ok(PNG))
        self.assertTrue(server.sniff_ok(JPG))
        self.assertFalse(server.sniff_ok(b"<html>not an image</html>"))

    def test_upload_rejects_fake_image(self):
        fake = "data:image/jpeg;base64," + base64.b64encode(b"MZ this is an exe").decode()
        with self.assertRaises(server.BadRequest):
            server.save_uploads([{"name": "x.jpg", "data": fake}])

    def test_upload_rejects_wrong_extension(self):
        with self.assertRaises(server.BadRequest):
            server.save_uploads([{"name": "x.gif", "data": base64.b64encode(PNG).decode()}])


if __name__ == "__main__":
    unittest.main()
