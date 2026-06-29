import logging
import unittest
from unittest.mock import MagicMock, patch

from sighthouse.frontend.runner import LocalApiClient


def _response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp


class TestLocalApiClient(unittest.TestCase):
    def setUp(self):
        self.client = LocalApiClient(
            logging.getLogger("test_runner"), base_url="http://x/api/v1"
        )

    @patch("sighthouse.frontend.runner.requests")
    def test_delete_all_functions_hits_correct_url(self, mock_requests):
        mock_requests.delete.return_value = _response(200)
        self.client.delete_all_functions(1, 2)
        mock_requests.delete.assert_called_once()
        url = mock_requests.delete.call_args[0][0]
        self.assertEqual(url, "http://x/api/v1/programs/1/sections/2/functions")

    @patch("sighthouse.frontend.runner.requests")
    def test_update_status_sends_payload(self, mock_requests):
        mock_requests.put.return_value = _response(200)
        self.client.update_status(7, "running", "50%")
        _, kwargs = mock_requests.put.call_args
        self.assertEqual(kwargs["json"], {"status": "running", "progress": "50%"})

    @patch("sighthouse.frontend.runner.requests")
    def test_create_functions_batches_requests(self, mock_requests):
        # Two batches when count exceeds BATCH_SIZE.
        self.client.BATCH_SIZE = 2
        mock_requests.post.return_value = _response(
            201, {"functions": [{"id": 10}, {"id": 11}]}
        )
        functions = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
        self.client.create_functions(1, 2, functions)

        self.assertEqual(mock_requests.post.call_count, 2)  # 2 + 1
        # IDs from the response are written back into the input dicts.
        self.assertEqual(functions[0]["id"], 10)
        self.assertEqual(functions[1]["id"], 11)

    @patch("sighthouse.frontend.runner.requests")
    def test_create_functions_handles_failure_status(self, mock_requests):
        mock_requests.post.return_value = _response(500)
        functions = [{"name": "a"}]
        # Should not raise even when the server reports an error.
        self.client.create_functions(1, 2, functions)
        self.assertNotIn("id", functions[0])

    @patch("sighthouse.frontend.runner.requests")
    def test_create_matches_posts_to_function_url(self, mock_requests):
        mock_requests.post.return_value = _response(201)
        self.client.create_matches(1, 2, 3, [{"name": "m"}])
        url = mock_requests.post.call_args[0][0]
        self.assertEqual(
            url, "http://x/api/v1/programs/1/sections/2/functions/3/matches"
        )
        _, kwargs = mock_requests.post.call_args
        self.assertEqual(kwargs["json"], {"matches": [{"name": "m"}]})

    @patch("sighthouse.frontend.runner.requests")
    def test_create_matches_empty_list_makes_no_request(self, mock_requests):
        self.client.create_matches(1, 2, 3, [])
        mock_requests.post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
