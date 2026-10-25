import unittest

from backend.detection_types import is_person_class


class DetectionTypesTest(unittest.TestCase):
    def test_person_aliases_are_treated_as_human(self):
        for value in ("person", "Person", "human", "people", "pedestrian", "0"):
            with self.subTest(value=value):
                self.assertTrue(is_person_class(value))

    def test_non_person_classes_are_not_treated_as_human(self):
        for value in ("drone", "fire_extinguisher", "", None):
            with self.subTest(value=value):
                self.assertFalse(is_person_class(value))


if __name__ == "__main__":
    unittest.main()
