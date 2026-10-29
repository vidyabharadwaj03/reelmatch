import base64
import unittest

from app import server
from app.planner import make_plan
from app.registry import choose

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


class ChooserTests(unittest.TestCase):
    def test_many_photos_long_video_with_sound_picks_seedance(self):
        self.assertEqual(choose({"duration": 15}, 5)["model"], "seedance-2.5-draft")

    def test_single_photo_short_silent_product_picks_cheaper_wan(self):
        r = choose({"duration": 5, "needs_audio": False, "subject": "product"}, 1)
        self.assertEqual(r["model"], "wan-2.7-i2v")
        self.assertEqual(r["cost"], 106)

    def test_sound_requirement_rules_out_wan(self):
        self.assertEqual(choose({"duration": 5}, 1)["model"], "seedance-2.5-draft")

    def test_long_video_only_seedance_fits(self):
        self.assertEqual(choose({"duration": 25}, 3)["model"], "seedance-2.5-draft")

    def test_verified_likeness_has_no_wired_model(self):
        r = choose({"duration": 15, "verified_likeness": True}, 2)
        self.assertIsNone(r["model"])

    def test_budget_too_small_means_no_model(self):
        self.assertIsNone(choose({"duration": 5, "budget": 100}, 1)["model"])

    def test_unwired_models_never_win(self):
        for r in choose({"duration": 15}, 5)["ranking"]:
            if r["status"] == "listed":
                self.assertFalse(r["eligible"])

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

    def test_people_prefer_model_that_accepted_real_faces(self):
        self.assertEqual(choose({"duration": 5, "subject": "people", "needs_audio": False}, 1)["model"], "seedance-2.5-draft")

    def test_open_weights_only_finds_nothing_wired(self):
        self.assertIsNone(choose({"duration": 15, "subject": "product", "open_weights_only": True}, 3)["model"])

    def test_every_listed_model_has_evidence(self):
        for r in choose({"duration": 15}, 3)["ranking"]:
            self.assertTrue(r["evidence"], r["id"])

    def test_blog_evidence_always_has_a_source_link_or_is_ran_comfy(self):
        for r in choose({"duration": 15}, 3)["ranking"]:
            for e in r["evidence"]:
                if e["kind"] == "blog":
                    self.assertTrue(e["url"], r["id"])


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
