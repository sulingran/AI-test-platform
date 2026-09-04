import os
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.core.real_env_token import fetch_real_env_token


class RealEnvTokenConfigTests(SimpleTestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_missing_configuration_returns_none_without_request(self):
        with patch("apps.core.real_env_token.requests.post") as post:
            self.assertIsNone(fetch_real_env_token())
            post.assert_not_called()

    @patch.dict(
        os.environ,
        {
            "REAL_ENV_BASE_URL": "https://example.test:9993/",
            "REAL_ENV_USERNAME": "tester",
            "REAL_ENV_PASSWORD": "secret",
        },
        clear=True,
    )
    def test_tls_verification_is_enabled_by_default(self):
        response = Mock()
        response.json.return_value = {"data": {"accessToken": "token-value"}}
        with patch("apps.core.real_env_token.requests.post", return_value=response) as post:
            self.assertEqual(fetch_real_env_token(), "token-value")
        post.assert_called_once_with(
            "https://example.test:9993/uap-change-service/oauth/token",
            data={"userName": "tester", "password": "secret", "loginType": "2"},
            timeout=25,
            verify=True,
        )

    @patch.dict(
        os.environ,
        {
            "REAL_ENV_BASE_URL": "https://example.test:9993",
            "REAL_ENV_USERNAME": "tester",
            "REAL_ENV_PASSWORD": "secret",
            "REAL_ENV_VERIFY_SSL": "false",
        },
        clear=True,
    )
    def test_tls_verification_can_be_explicitly_disabled(self):
        response = Mock()
        response.json.return_value = {"data": {"accessToken": "token-value"}}
        with patch("apps.core.real_env_token.requests.post", return_value=response) as post:
            self.assertEqual(fetch_real_env_token(), "token-value")
        self.assertEqual(post.call_args.kwargs["verify"], False)
