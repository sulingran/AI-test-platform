"""token 自动刷新（治本）的单元测试。

覆盖 apps/api_testing/utils.py 里新增的两个 helper 和 execute_test_suite 的
「401 → 自动重登换 token → 重试一次」逻辑。全部用 mock，不访问真实 DB/网络。
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.api_testing.utils import (
    _apply_refreshed_token,
    _is_token_expired,
    _refresh_env_token,
)


def _make_response(status_code, content_type='application/json', text='{"code":0}'):
    resp = SimpleNamespace(
        status_code=status_code,
        headers={'content-type': content_type},
        text=text,
    )
    resp.json = MagicMock(return_value={'code': 0})
    return resp


class TokenExpiredDetectionTests(SimpleTestCase):
    def test_http_401_is_token_expired(self):
        self.assertTrue(_is_token_expired(_make_response(401)))

    def test_non_401_is_not_token_expired(self):
        self.assertFalse(_is_token_expired(_make_response(200)))
        self.assertFalse(_is_token_expired(_make_response(400)))
        self.assertFalse(_is_token_expired(_make_response(500)))


class RefreshEnvTokenTests(SimpleTestCase):
    def test_success_writes_and_returns_true(self):
        env = SimpleNamespace(variables={'token': 'OLD'}, save=MagicMock())
        with patch('apps.api_testing.utils.fetch_real_env_token_detail',
                   return_value=('NEW_TOKEN', None)) as mk_fetch, \
             patch('apps.api_testing.utils.write_token_to_environment') as mk_write:
            self.assertTrue(_refresh_env_token(env))
            mk_fetch.assert_called_once_with()
            mk_write.assert_called_once_with(env, 'NEW_TOKEN')

    def test_login_failure_returns_false_without_write(self):
        env = SimpleNamespace(variables={'token': 'OLD'}, save=MagicMock())
        with patch('apps.api_testing.utils.fetch_real_env_token_detail',
                   return_value=(None, '登录被拒绝')) as mk_fetch, \
             patch('apps.api_testing.utils.write_token_to_environment') as mk_write:
            self.assertFalse(_refresh_env_token(env))
            mk_write.assert_not_called()

    def test_none_environment_is_false(self):
        self.assertFalse(_refresh_env_token(None))


class ApplyRefreshedTokenTests(SimpleTestCase):
    def test_plain_string_token(self):
        headers = {'Authorization': 'Bearer OLD'}
        env = SimpleNamespace(variables={'token': 'NEW'})
        _apply_refreshed_token(headers, env)
        self.assertEqual(headers['Authorization'], 'Bearer NEW')

    def test_dict_shaped_token(self):
        headers = {'Authorization': 'Bearer OLD'}
        env = SimpleNamespace(variables={'token': {'currentValue': 'CUR', 'initialValue': 'INIT'}})
        _apply_refreshed_token(headers, env)
        self.assertEqual(headers['Authorization'], 'Bearer CUR')

    def test_no_authorization_header_unchanged(self):
        headers = {'X-Custom': '1'}
        env = SimpleNamespace(variables={'token': 'NEW'})
        _apply_refreshed_token(headers, env)
        self.assertEqual(headers, {'X-Custom': '1'})


class ExecuteTestSuiteRetryTests(SimpleTestCase):
    def _make_suite_request(self):
        api_request = SimpleNamespace(
            name='dept-get',
            method='GET',
            url='https://192.168.159.114:9993/sysmgr/dept/get/1',
            headers=[{'enabled': True, 'key': 'Authorization', 'value': 'Bearer {{token}}'}],
            params={},
            body={},
            assertions=[],
        )
        suite_request = SimpleNamespace(
            request=api_request,
            assertions=[{'type': 'status_code', 'value': 200}],
            extract_vars=[],
        )
        return suite_request

    def _make_suite(self, suite_request):
        qs = MagicMock()
        qs.count.return_value = 1
        qs.__iter__.return_value = iter([suite_request])
        suite = MagicMock()
        suite.testsuiterequest_set.filter.return_value.order_by.return_value = qs
        return suite

    def _make_environment(self):
        return SimpleNamespace(variables={'token': 'OLD_TOKEN', 'verify_ssl': False},
                               save=MagicMock())

    @patch('apps.api_testing.utils.fetch_real_env_token_detail')
    @patch('requests.request')
    @patch('apps.api_testing.models.RequestHistory.objects.create')
    @patch('apps.api_testing.models.TestExecution.objects.create')
    def test_401_triggers_refresh_and_retry(self, mk_exec, mk_history, mk_request, mk_fetch):
        from apps.api_testing.utils import execute_test_suite

        mk_request.side_effect = [_make_response(401), _make_response(200)]
        mk_fetch.return_value = ('NEW_TOKEN', None)

        result = execute_test_suite(
            self._make_suite(self._make_suite_request()),
            self._make_environment(),
            SimpleNamespace(id=1),
        )

        self.assertTrue(result['success'])
        self.assertEqual(mk_request.call_count, 2)
        mk_fetch.assert_called_once_with()
        first = result['results'][0]
        self.assertTrue(first['token_refreshed'])
        self.assertTrue(first['passed'])
        self.assertEqual(result['passed_count'], 1)
        self.assertEqual(result['failed_count'], 0)

    @patch('apps.api_testing.utils.fetch_real_env_token_detail')
    @patch('requests.request')
    @patch('apps.api_testing.models.RequestHistory.objects.create')
    @patch('apps.api_testing.models.TestExecution.objects.create')
    def test_refresh_failure_does_not_retry(self, mk_exec, mk_history, mk_request, mk_fetch):
        from apps.api_testing.utils import execute_test_suite

        mk_request.side_effect = [_make_response(401)]
        mk_fetch.return_value = (None, '登录被拒绝')

        result = execute_test_suite(
            self._make_suite(self._make_suite_request()),
            self._make_environment(),
            SimpleNamespace(id=1),
        )

        self.assertEqual(mk_request.call_count, 1)
        first = result['results'][0]
        self.assertFalse(first['token_refreshed'])
        self.assertFalse(first['passed'])
        self.assertEqual(result['failed_count'], 1)

    @patch('apps.api_testing.utils.fetch_real_env_token_detail')
    @patch('requests.request')
    @patch('apps.api_testing.models.RequestHistory.objects.create')
    @patch('apps.api_testing.models.TestExecution.objects.create')
    def test_non_401_does_not_touch_token(self, mk_exec, mk_history, mk_request, mk_fetch):
        from apps.api_testing.utils import execute_test_suite

        mk_request.side_effect = [_make_response(200)]

        result = execute_test_suite(
            self._make_suite(self._make_suite_request()),
            self._make_environment(),
            SimpleNamespace(id=1),
        )

        self.assertEqual(mk_request.call_count, 1)
        mk_fetch.assert_not_called()
        first = result['results'][0]
        self.assertFalse(first['token_refreshed'])
        self.assertTrue(first['passed'])