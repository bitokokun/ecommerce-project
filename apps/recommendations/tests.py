"""
Tests for the recommendation engine. They use plain data, no database, so they
run in a fraction of a second:

    python manage.py test apps.recommendations
"""
import unittest

from .engine import Recommender, tokenize

PRODUCTS = [
    {"id": 1, "name": "Wireless Mouse", "category": "Computers & Laptops",
     "description": "Compact wireless mouse with USB receiver for laptop and desktop."},
    {"id": 2, "name": "Gaming Mouse", "category": "Computers & Laptops",
     "description": "RGB gaming mouse with adjustable DPI and programmable buttons."},
    {"id": 3, "name": "Mechanical Keyboard", "category": "Computers & Laptops",
     "description": "Mechanical keyboard with RGB backlight and USB cable."},
    {"id": 4, "name": "Cotton T-Shirt", "category": "Men's Fashion",
     "description": "Soft cotton t-shirt in many colors."},
    {"id": 5, "name": "Running Shoes", "category": "Shoes",
     "description": "Lightweight running shoes with breathable mesh."},
    {"id": 6, "name": "Ceramic Mug", "category": "Home & Kitchen",
     "description": "Large ceramic mug for coffee and tea."},
    {"id": 7, "name": "Coffee Beans", "category": "Groceries & Food",
     "description": "Whole roasted coffee beans, medium roast."},
]


def ids(results):
    return [r[0] for r in results]


class TokenizeTests(unittest.TestCase):
    def test_lowercases_and_drops_stopwords_and_numbers(self):
        self.assertEqual(tokenize("The Mouse and 2024"), ["mouse"])

    def test_plurals_are_merged(self):
        self.assertEqual(tokenize("Headphones"), tokenize("headphone"))

    def test_empty_and_none(self):
        self.assertEqual(tokenize(""), [])
        self.assertEqual(tokenize(None), [])

    def test_non_latin_text_is_kept(self):
        self.assertEqual(tokenize("موس بی سیم"), ["موس", "بی", "سیم"])


class SimilarTests(unittest.TestCase):
    def setUp(self):
        self.model = Recommender(PRODUCTS, orders=[])

    def test_related_products_rank_first(self):
        result = self.model.similar(1)
        self.assertEqual(result[0][0], 2)          # the other mouse is closest
        self.assertIn(3, ids(result))              # keyboard shares "USB", category

    def test_unrelated_products_are_left_out(self):
        self.assertNotIn(5, ids(self.model.similar(4)))   # t-shirt vs shoes
        self.assertEqual(self.model.similar(5), [])       # nothing resembles shoes

    def test_never_returns_the_product_itself(self):
        self.assertNotIn(1, ids(self.model.similar(1)))

    def test_limit_is_respected(self):
        self.assertLessEqual(len(self.model.similar(1, limit=1)), 1)

    def test_unknown_product_gives_empty_list(self):
        self.assertEqual(self.model.similar(999), [])

    def test_works_with_no_sales_at_all(self):
        self.assertTrue(self.model.similar(1))     # cold start still recommends


class CoPurchaseTests(unittest.TestCase):
    def test_bought_together_surfaces_text_unrelated_items(self):
        orders = [[4, 5], [4, 5], [4, 5]]          # shirt + shoes, three times
        model = Recommender(PRODUCTS, orders)
        result = model.similar(4)
        self.assertEqual(ids(result), [5])
        self.assertEqual(result[0][2], "Often bought together")

    def test_one_off_order_is_weaker_than_repeated_orders(self):
        few = Recommender(PRODUCTS, [[4, 5], [4], [5], [4], [5]])
        many = Recommender(PRODUCTS, [[4, 5]] * 5)
        self.assertLess(few.copurchase_sim(4, 5), many.copurchase_sim(4, 5))

    def test_orders_with_unknown_products_do_not_crash(self):
        model = Recommender(PRODUCTS, [[1, 99], [99]])    # 99 = inactive/deleted
        self.assertEqual(model.copurchase_sim(1, 99), 0.0)


class ForUserTests(unittest.TestCase):
    def setUp(self):
        self.model = Recommender(PRODUCTS, orders=[])

    def test_no_history_means_no_recommendations(self):
        self.assertEqual(self.model.for_user([], []), [])

    def test_recommends_related_and_explains_why(self):
        result = self.model.for_user(bought=[1])
        self.assertEqual(result[0][0], 2)
        self.assertEqual(result[0][2], "Because you bought Wireless Mouse")

    def test_never_recommends_what_they_already_bought(self):
        self.assertNotIn(1, ids(self.model.for_user(bought=[1])))

    def test_never_recommends_what_is_already_in_the_cart(self):
        self.assertNotIn(2, ids(self.model.for_user(bought=[1], in_cart=[2])))

    def test_cart_counts_but_less_than_a_purchase(self):
        from_cart = self.model.for_user([], in_cart=[1])
        from_buy = self.model.for_user([1], [])
        self.assertEqual(from_cart[0][2], "Goes well with Wireless Mouse in your cart")
        self.assertLess(from_cart[0][1], from_buy[0][1])

    def test_unknown_products_in_history_are_ignored(self):
        self.assertEqual(self.model.for_user(bought=[999]), [])


if __name__ == "__main__":
    unittest.main()
