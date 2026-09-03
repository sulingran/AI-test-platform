"""自动登录真实环境并更新环境变量中的 token。

用法：
    python manage.py refresh_token
自动获取新 token 并写回各环境的 token 变量（currentValue/initialValue），
省去每次手动复制粘贴。
"""
from django.core.management.base import BaseCommand

from apps.core.real_env_token import (
    decode_jwt_exp,
    fetch_real_env_token,
    write_token_to_environment,
)


class Command(BaseCommand):
    help = "自动登录真实环境，更新各环境变量中的 token"

    def handle(self, *args, **options):
        from apps.api_testing.models import Environment

        token = fetch_real_env_token()
        if not token:
            self.stdout.write(self.style.ERROR("获取 token 失败，未更新任何环境变量"))
            return

        exp = decode_jwt_exp(token)
        updated = []
        for env in Environment.objects.all():
            variables = env.variables or {}
            if "token" not in variables:
                continue
            write_token_to_environment(env, token)
            updated.append((env.id, env.name, env.get_scope_display()))

        if updated:
            self.stdout.write(self.style.SUCCESS("已更新 %d 个环境的 token：" % len(updated)))
            for eid, name, scope in updated:
                self.stdout.write("    - #%d %s (%s)" % (eid, name, scope))
            if exp:
                self.stdout.write(self.style.SUCCESS("token 过期时间：%s" % exp))
        else:
            self.stdout.write(self.style.WARNING("没有找到含 token 变量的环境，未做改动"))