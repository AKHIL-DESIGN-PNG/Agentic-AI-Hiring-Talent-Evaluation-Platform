import unittest

from backend.reference_solvers import solve_reference_case


class ReferenceSolversTest(unittest.TestCase):
    def test_trapping_rain_water_custom_case(self):
        self.assertEqual(solve_reference_case("trapping_rain_water", "[2,0,2]"), "2")

    def test_remove_element_count_custom_case(self):
        self.assertEqual(solve_reference_case("remove_element_count", "[[3,2,2,3],3]"), "2")

    def test_palindrome_number_custom_case(self):
        self.assertEqual(solve_reference_case("palindrome_number", "121"), "true")


if __name__ == "__main__":
    unittest.main()
