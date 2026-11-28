"""Checks the gag-selection preview math without starting the game."""
import importlib.util
import pathlib
import unittest

MODULE = pathlib.Path(__file__).resolve().parents[1] / 'battle-src/client/toontown/battle/BattleSelectionMath.py'
spec = importlib.util.spec_from_file_location('battle_selection_math', MODULE)
math = importlib.util.module_from_spec(spec)
spec.loader.exec_module(math)


class PreviewMath(unittest.TestCase):
    def test_block_keeps_a_minimum_hit(self):
        self.assertEqual(math.block_damage(10), 5)
        self.assertEqual(math.block_damage(1), 1)
        self.assertEqual(math.block_damage(0), 0)
        self.assertEqual(math.block_damage(-3), 0)

    def test_accuracy_uses_calculator_pieces(self):
        # Throw cupcake: table accuracy 75, no experience, no suit defense.
        self.assertEqual(math.accuracy(75, 0, 0, math.THROW), 75)
        # Suit defense is subtracted, then clamped.
        self.assertEqual(math.accuracy(75, 0, 10, math.THROW), 65)
        # Experience band 2 adds 20.
        self.assertEqual(math.accuracy(75, 2, 0, math.THROW), 95)
        # Cap at the calculator's MaxToonAcc.
        self.assertEqual(math.accuracy(90, 6, 0, math.THROW), 95)

    def test_lure_and_drop_special_cases(self):
        self.assertEqual(math.accuracy(50, 0, 0, math.DROP, all_targets_lured=True), 0)
        self.assertEqual(math.accuracy(75, 0, 0, math.THROW, all_targets_lured=True, target_count=2), 100)
        self.assertIsNone(math.accuracy(0, 0, 0, math.TRAP))

    def test_group_heal_splits(self):
        self.assertEqual(math.split_amount(12, math.HEAL, True, 3), 4)
        self.assertEqual(math.split_amount(12, math.THROW, True, 3), 12)

    def test_conflict_is_identified_once(self):
        entries = [
            {'track': math.TRAP, 'amount': 10, 'target': 1, 'group': False, 'confirmed': True, 'label': 'Banana', 'lured': False},
            {'track': math.TRAP, 'amount': 20, 'target': 1, 'group': False, 'confirmed': False, 'label': 'Rake', 'lured': False},
        ]
        summary = math.team_summary(entries)
        keys = [key for key, _text in summary['conflicts']]
        self.assertIn('trap-1', keys)
        self.assertEqual(keys.count('trap-1'), 1)
        self.assertTrue(any('not confirmed' in note for note in summary['notes']))

    def test_same_track_note(self):
        entries = [
            {'track': math.THROW, 'amount': 5, 'target': 0, 'group': False, 'confirmed': True, 'label': 'Cupcake', 'targets': 1, 'lured': False},
            {'track': math.THROW, 'amount': 8, 'target': 0, 'group': False, 'confirmed': True, 'label': 'Fruit', 'targets': 1, 'lured': False},
        ]
        summary = math.team_summary(entries)
        self.assertEqual(summary['damage'], 13)
        self.assertTrue(any('single accuracy roll' in note for note in summary['notes']))


if __name__ == '__main__':
    unittest.main()
