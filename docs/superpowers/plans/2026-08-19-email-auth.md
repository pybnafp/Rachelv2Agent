# 邮箱验证账号体系（Plan B + 清库重建）实施计划

> Spec 决策（已确认）：仅邮箱注册登录；注册需邮箱验证码（6位/10分钟/60s重发冷却/5次尝试）；登录=邮箱+密码（未验证→403 引导）；旧 users+jobs 全清（保留 llm_providers）；首个**完成验证**的用户获 admin；发信=SMTP 465/SSL（凭据未到位前 EMAIL_BACKEND=console 打日志）。

## 后端（T1）

- Settings+: `EMAIL_BACKEND(console|smtp)`, `SMTP_HOST/PORT=465/USER/PASS/FROM`, `CODE_TTL_MIN=10`, `RESEND_COOLDOWN_SEC=60`
- 迁移 0003：DELETE job_steps/jobs/users → users 加 `email`(unique non-null)+`is_verified`(bool default false)，drop `username`
- `app/services/email.py`：`send_code(email, code)`；console 后端记录到模块级 `SENT:list`（供测试读）+日志；smtp 用 smtplib.SMTP_SSL
- 表 `email_codes`(email, code_hash, purpose, expires_at, used, attempts, created_at)
- API：register(email,pw)→校验格式/密码≥6/已验证邮箱409/未验证则更新密码重发；发码成功 202。verify(email,code)→通过则 is_verified+发 token（若 verified 计数==0 → role=admin）。resend→冷却 429。login→未验证 403 "邮箱未验证"。/me 返回 email
- 验证码：sha256 存储；比对 attempts<5、TTL、一次性
- conftest：`verified_headers(client, email)` 助手（console 后端读 SENT 码走 verify）；全量测试改造

## 前端（T2）

- RegisterPage 两步：①邮箱+密码→register ②验证码(6位)+60s倒计时重发→verify→登录态
- LoginPage：403 未验证→切到验证码步（预填邮箱）；?changed=1 横幅保留
- 账户 chip/改密弹窗：label 适配 email
- hooks: useRegister/useVerify/useResend（或直接 api()）

## 部署（T3，控制器）

- scp 后端文件+前端构建；**alembic upgrade head（执行清库迁移）**；重启；注册→console 日志取码→verify→admin；用户填 SMTP_* 后改 EMAIL_BACKEND=smtp 重启即真发信
- ops.md 记录
