"""Offline regression tests: no Telegram/Gemini calls or credentials."""
import ast
import logging
import os
from pathlib import Path
import random
import re
import tempfile
import unittest
from pydub import AudioSegment
from pydub.generators import Sine

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'main.py').read_text(encoding='utf-8')
tree = ast.parse(source)
names = {'mix_audio_with_music', 'clean_body_script', 'get_random_music_file'}
namespace = dict(AudioSegment=AudioSegment, logger=logging.getLogger('test'),
                 os=os, random=random, re=re, FADE_DURATION_MS=2000)
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[]), 'main.py', 'exec'), namespace)

class LayoutTests(unittest.TestCase):
    def test_music_after_speech_both_sections(self):
        with tempfile.TemporaryDirectory() as folder:
            speech = Sine(440, sample_rate=24000).to_audio_segment(duration=1200).apply_gain(-15)
            music = Sine(880, sample_rate=24000).to_audio_segment(duration=5000)
            sp, mu, out = [str(Path(folder) / n) for n in ('speech.wav', 'music.wav', 'out.wav')]
            speech.export(sp, format='wav').close()
            music.export(mu, format='wav').close()
            for intro in (True, False):
                namespace['mix_audio_with_music'](sp, out, mu, intro)
                result = AudioSegment.from_wav(out)
                self.assertEqual(len(result), 6200)
                self.assertEqual(result[:1200].raw_data, speech.raw_data)
                self.assertGreater(result[3200:3700].rms, 0)
                self.assertLess(result[1200:1300].rms, result[3200:3300].rms)
                self.assertLess(result[-100:].rms, result[3200:3300].rms)

    def test_body_deduplication(self):
        script = 'فرشید: سلام و درود خدمت شنوندگان عزیز\nفرشید: خبر امروز\nفرشید: این بود خلاصه‌ی اخبار'
        self.assertEqual(namespace['clean_body_script'](script, 'فرشید'), 'فرشید: خبر امروز')
        with self.assertRaises(ValueError):
            namespace['clean_body_script']('فرشید: این بود خلاصه', 'فرشید')

    def test_single_and_multiple_files(self):
        with tempfile.TemporaryDirectory() as folder:
            choose = namespace['get_random_music_file']
            self.assertIsNone(choose(folder))
            first = Path(folder) / 'one.mp3'
            first.touch()
            self.assertEqual(Path(choose(folder)), first)
            second = Path(folder) / 'two.wav'
            second.touch()
            for _ in range(20):
                self.assertIn(Path(choose(folder)), {first, second})

    def test_repository_mp3_files_decode(self):
        files = sorted((ROOT / 'assets').glob('*_music/*.mp3'))
        self.assertTrue(files, 'No music assets found')
        for path in files:
            audio = AudioSegment.from_file(path)
            self.assertGreater(len(audio), 0, str(path))
            self.assertGreater(audio.rms, 0, str(path))

if __name__ == '__main__':
    unittest.main()
