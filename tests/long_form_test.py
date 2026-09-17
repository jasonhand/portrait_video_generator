import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from long_form.analysis import AnalysisResult
from long_form.cli import validate_plan
from long_form.models import EditPlan, Scene, SourceInfo
from long_form.renderer import probe_output, render_plan
from long_form.scheduler import build_edit_plan
from long_form.sources import common_interval, parse_streamyard_offset, probe_source


def source(name, kind, offset=0.0, duration=90.0, has_audio=True):
    return SourceInfo(
        path=f"/tmp/{name}",
        name=name,
        kind=kind,
        offset=offset,
        duration=duration,
        width=1920,
        height=1080,
        fps=30.0,
        has_audio=has_audio,
    )


class SourceTests(unittest.TestCase):
    def test_streamyard_offset(self):
        path = Path("Episode-Jason-screen-01h_02m_03s_456ms-StreamYard.mp4")
        self.assertAlmostEqual(parse_streamyard_offset(path), 3723.456)
        self.assertEqual(parse_streamyard_offset(Path("camera.mp4")), 0.0)

    def test_common_interval_uses_overlap(self):
        sources = [
            source("a.mp4", "webcam", offset=0.2, duration=20),
            source("b.mp4", "webcam", offset=1.0, duration=18),
            source("screen.mp4", "screen", offset=0.5, duration=25),
        ]
        start, duration = common_interval(sources)
        self.assertEqual(start, 1.0)
        self.assertAlmostEqual(duration, 18.0)


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.sources = [
            source("alex-webcam.mp4", "webcam"),
            source("blair-webcam.mp4", "webcam"),
            source("demo-screen.mp4", "screen", has_audio=False),
        ]
        samples = 180
        self.analysis = AnalysisResult(
            audio_interval=0.5,
            audio_levels={
                "alex-webcam.mp4": [0.08 if i < samples // 2 else 0.005 for i in range(samples)],
                "blair-webcam.mp4": [0.005 if i < samples // 2 else 0.08 for i in range(samples)],
            },
            screen_interval=1.0,
            screen_scores=[5.0] * 90,
            screen_active=[True] * 90,
        )

    def test_plan_is_reproducible_and_valid(self):
        first = build_edit_plan("episode", self.sources, 0.0, 90.0, self.analysis, 42)
        second = build_edit_plan("episode", self.sources, 0.0, 90.0, self.analysis, 42)
        self.assertEqual(first.to_dict(), second.to_dict())
        validate_plan(first)
        self.assertEqual(first.scenes[0].start, 0.0)
        self.assertEqual(first.scenes[-1].end, 90.0)

    def test_plan_uses_sources_and_hybrid_palette(self):
        plan = build_edit_plan("episode", self.sources, 0.0, 90.0, self.analysis, 17)
        types = {scene.scene_type for scene in plan.scenes}
        displayed_webcams = {
            scene.source for scene in plan.scenes if scene.scene_type.startswith("webcam")
        }
        self.assertEqual(displayed_webcams, {"alex-webcam.mp4", "blair-webcam.mp4"})
        self.assertIn("screen_pip", types)
        self.assertTrue(types.intersection({"webcam_full", "webcam_zoom"}))
        first_screen_activity = 0.0
        first_screen_scene = next(
            scene for scene in plan.scenes if scene.scene_type.startswith("screen")
        )
        self.assertLessEqual(first_screen_scene.start, first_screen_activity + 30.0)
        self.assertTrue(
            all(scene.pip_source for scene in plan.scenes if scene.scene_type == "screen_pip")
        )
        self.assertTrue(
            all(
                scene.pip_position == "upper_right"
                for scene in plan.scenes
                if scene.scene_type == "screen_pip"
            )
        )
        webcam_scenes = [scene for scene in plan.scenes if scene.scene_type.startswith("webcam")]
        zoom_rate = sum(scene.scene_type == "webcam_zoom" for scene in webcam_scenes) / len(webcam_scenes)
        self.assertLessEqual(zoom_rate, 0.35)

        screen_runs = []
        run_start = None
        run_end = None
        for scene in plan.scenes:
            if scene.scene_type == "screen_pip":
                if run_start is None:
                    run_start = scene.start
                run_end = scene.end
            elif run_start is not None:
                screen_runs.append((run_start, run_end))
                run_start = run_end = None
        if run_start is not None:
            screen_runs.append((run_start, run_end))
        self.assertTrue(screen_runs)
        for start, end in screen_runs:
            self.assertGreaterEqual(end - start, 20.0)
            self.assertLessEqual(end - start, 30.0)
        for previous, current in zip(screen_runs, screen_runs[1:]):
            self.assertGreaterEqual(current[0] - previous[1], 8.0)
        webcam_scenes = [scene for scene in plan.scenes if scene.scene_type.startswith("webcam")]
        self.assertTrue(
            all(scene.source == "alex-webcam.mp4" for scene in webcam_scenes if scene.end <= 45.0)
        )
        self.assertTrue(
            all(scene.source == "blair-webcam.mp4" for scene in webcam_scenes if scene.start >= 45.0)
        )


class RendererTests(unittest.TestCase):
    def _make_video(self, path: Path, color: str, frequency: int = 440, audio=True):
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=640x360:r=30:d=8",
        ]
        if audio:
            command.extend(
                ["-f", "lavfi", "-i", f"sine=frequency={frequency}:sample_rate=48000:duration=8"]
            )
        command.extend(["-t", "8", "-c:v", "libx264", "-pix_fmt", "yuv420p"])
        if audio:
            command.extend(["-c:a", "aac", "-shortest"])
        else:
            command.append("-an")
        command.extend(["-y", str(path)])
        subprocess.run(command, check=True)

    def test_all_scene_types_render_to_landscape_mp4(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            webcam_a = root / "test-alex-webcam.mp4"
            webcam_b = root / "test-blair-webcam.mp4"
            screen = root / "test-demo-screen.mp4"
            self._make_video(webcam_a, "blue", 440)
            self._make_video(webcam_b, "red", 660)
            self._make_video(screen, "green", audio=False)
            sources = [probe_source(webcam_a), probe_source(webcam_b), probe_source(screen)]
            plan = EditPlan(
                version=1,
                episode="test",
                seed=1,
                common_start=0.0,
                duration=8.0,
                sources=sources,
                scenes=[
                    Scene(0.0, 2.0, webcam_a.name, "webcam_full"),
                    Scene(2.0, 4.0, webcam_b.name, "webcam_zoom", zoom=1.1),
                    Scene(4.0, 6.0, screen.name, "screen_full"),
                    Scene(
                        6.0,
                        8.0,
                        screen.name,
                        "screen_pip",
                        pip_source=webcam_a.name,
                        pip_position="upper_right",
                    ),
                ],
            )
            plan_path = root / "plan.json"
            plan.save(plan_path)
            self.assertEqual(EditPlan.load(plan_path).to_dict(), plan.to_dict())

            output = root / "output.mp4"
            render_plan(plan, output)
            probe = probe_output(output)
            video = next(stream for stream in probe["streams"] if stream["codec_type"] == "video")
            audio = next(stream for stream in probe["streams"] if stream["codec_type"] == "audio")
            self.assertEqual((video["width"], video["height"]), (1920, 1080))
            self.assertEqual(video["codec_name"], "h264")
            self.assertEqual(audio["codec_name"], "aac")
            self.assertAlmostEqual(float(probe["format"]["duration"]), 8.0, delta=0.2)


if __name__ == "__main__":
    unittest.main()
