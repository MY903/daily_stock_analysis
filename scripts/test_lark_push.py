#!/usr/bin/env python3
"""
Lark Push Diagnostic Script

Tests the full Lark API pipeline step by step, showing actual API responses
instead of just True/False. Helps diagnose why cards aren't being received.

Usage:
    cd /path/to/project && python scripts/test_lark_push.py
"""

import json
import logging
import os
import sys

# Ensure project root is on sys.path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Suppress SDK debug noise
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

# ──────────────────────────────────────────────────────────
# Step 0: Load config
# ──────────────────────────────────────────────────────────
print("=" * 72)
print("LARK PUSH DIAGNOSTIC")
print("=" * 72)

try:
    from config.settings import settings
except ImportError as e:
    print(f"\n[FATAL] Cannot import settings: {e}")
    print("Make sure you're running from the project root directory.")
    sys.exit(1)

APP_ID = settings.LARK_APP_ID
APP_SECRET = settings.LARK_APP_SECRET
DEFAULT_CHAT_ID = settings.LARK_DEFAULT_CHAT_ID

print(f"\n  LARK_APP_ID          = {APP_ID}")
print(f"  LARK_APP_SECRET      = {'***' + (APP_SECRET[-4:] if len(APP_SECRET) > 4 else '')}")
print(f"  LARK_DEFAULT_CHAT_ID = {DEFAULT_CHAT_ID}")

if not APP_ID or not APP_SECRET:
    print("\n[FAIL] LARK_APP_ID or LARK_APP_SECRET is empty. Check .env.")
    sys.exit(1)

# ──────────────────────────────────────────────────────────
# Step 1: SDK availability
# ──────────────────────────────────────────────────────────
print(f"\n{'─' * 72}")
print("STEP 1: SDK availability")
print(f"{'─' * 72}")

try:
    import lark_oapi as lark
    print("  [OK] lark-oapi is importable")
    print("  SDK location:", os.path.dirname(lark.__file__))
except ImportError as e:
    print(f"  [FAIL] lark-oapi not installed: {e}")
    sys.exit(1)

# ──────────────────────────────────────────────────────────
# Step 2: Get app_access_token (verifies credentials)
# ──────────────────────────────────────────────────────────
print(f"\n{'─' * 72}")
print("STEP 2: Get app_access_token (verify credentials)")
print(f"{'─' * 72}")

try:
    client = lark.Client.builder() \
        .app_id(APP_ID) \
        .app_secret(APP_SECRET) \
        .log_level(lark.LogLevel.ERROR) \
        .build()

    from lark_oapi.api.auth.v3.model.internal_app_access_token_request import \
        InternalAppAccessTokenRequest
    from lark_oapi.api.auth.v3.model.internal_app_access_token_request_body import \
        InternalAppAccessTokenRequestBody

    auth_request = InternalAppAccessTokenRequest.builder() \
        .request_body(
            InternalAppAccessTokenRequestBody.builder()
                .app_id(APP_ID)
                .app_secret(APP_SECRET)
                .build()
        ) \
        .build()

    auth_resp = client.auth.v3.app_access_token.internal(auth_request)

    print(f"  HTTP status:  {auth_resp.raw.status_code if auth_resp.raw else 'N/A'}")
    print(f"  code:         {auth_resp.code}")
    print(f"  msg:          {auth_resp.msg}")
    print(f"  log_id:       {auth_resp.get_log_id()}")

    if auth_resp.success():
        if auth_resp.raw:
            try:
                body = json.loads(auth_resp.raw.content)
                print(f"  token (first 20): {body.get('app_access_token', 'N/A')[:20]}...")
                print(f"  expire:           {body.get('expire', 'N/A')}")
            except (json.JSONDecodeError, TypeError):
                print("  (could not parse token from raw response)")
        print("  [OK] Credentials are valid")
    else:
        print("  [FAIL] Failed to get app_access_token")
        if auth_resp.raw:
            print(f"  Raw HTTP body: {auth_resp.raw.content[:500]}")

except Exception as e:
    print(f"  [ERROR] Exception: {e}")
    import traceback
    traceback.print_exc()

# ──────────────────────────────────────────────────────────
# Step 3: Get tenant_access_token
# ──────────────────────────────────────────────────────────
print(f"\n{'─' * 72}")
print("STEP 3: Get tenant_access_token")
print(f"{'─' * 72}")

try:
    from lark_oapi.api.auth.v3.model.internal_tenant_access_token_request import \
        InternalTenantAccessTokenRequest
    from lark_oapi.api.auth.v3.model.internal_tenant_access_token_request_body import \
        InternalTenantAccessTokenRequestBody

    tenant_req = InternalTenantAccessTokenRequest.builder() \
        .request_body(
            InternalTenantAccessTokenRequestBody.builder()
                .app_id(APP_ID)
                .app_secret(APP_SECRET)
                .build()
        ) \
        .build()

    tenant_resp = client.auth.v3.tenant_access_token.internal(tenant_req)

    print(f"  HTTP status:  {tenant_resp.raw.status_code if tenant_resp.raw else 'N/A'}")
    print(f"  code:         {tenant_resp.code}")
    print(f"  msg:          {tenant_resp.msg}")
    print(f"  log_id:       {tenant_resp.get_log_id()}")

    if tenant_resp.success():
        if tenant_resp.raw:
            try:
                body = json.loads(tenant_resp.raw.content)
                token = body.get('tenant_access_token', '')
                print(f"  token (first 20): {token[:20]}...")
                print(f"  expire:           {body.get('expire', 'N/A')}")
            except Exception:
                pass
        print("  [OK] Tenant token acquired")
    else:
        print("  [FAIL] Failed to get tenant_access_token")

except Exception as e:
    print(f"  [ERROR] Exception: {e}")

# ──────────────────────────────────────────────────────────
# Step 4: Try sending a test message (text type first)
# ──────────────────────────────────────────────────────────
print(f"\n{'─' * 72}")
print("STEP 4: Send test text message to LARK_DEFAULT_CHAT_ID")
print(f"{'─' * 72}")

if not DEFAULT_CHAT_ID:
    print("  [SKIP] LARK_DEFAULT_CHAT_ID is empty. Check .env.")
else:
    try:
        from lark_oapi.api.im.v1.model.create_message_request import \
            CreateMessageRequest
        from lark_oapi.api.im.v1.model.create_message_request_body import \
            CreateMessageRequestBody

        text_content = json.dumps({"text": "test from test_lark_push.py"})

        msg_request = CreateMessageRequest.builder() \
            .receive_id_type("chat_id") \
            .request_body(
                CreateMessageRequestBody.builder()
                    .receive_id(DEFAULT_CHAT_ID)
                    .content(text_content)
                    .msg_type("text")
                    .build()
            ) \
            .build()

        msg_response = client.im.v1.message.create(msg_request)

        print(f"  Target:       {DEFAULT_CHAT_ID}")
        print(f"  Msg type:     text")
        print(f"  HTTP status:  {msg_response.raw.status_code if msg_response.raw else 'N/A'}")
        print(f"  code:         {msg_response.code}")
        print(f"  msg:          {msg_response.msg}")
        print(f"  log_id:       {msg_response.get_log_id()}")

        if msg_response.raw:
            try:
                raw_body = json.loads(msg_response.raw.content)
                print(f"  Raw body:     {json.dumps(raw_body, indent=2, ensure_ascii=False)}")
            except (json.JSONDecodeError, TypeError):
                print(f"  Raw body:     {msg_response.raw.content[:500]}")

        if msg_response.success():
            print("  [OK] Text message sent successfully")
        else:
            print("  [FAIL] Failed to send text message")
            if msg_response.code == 10003:
                print("  -> INVALID CHAT_ID: The chat_id does not exist")
            elif msg_response.code == 99991663:
                print("  -> BOT NOT IN CHAT: The bot is not a member of this chat")
            elif msg_response.code == 99991669:
                print("  -> BOT PERMISSION DENIED: Bot lacks permission to send messages")
            elif msg_response.code == 99991600:
                print("  -> APP NOT ENABLED: The app is not enabled for this tenant")
            elif msg_response.code == 99991601:
                print("  -> APP NOT PUBLISHED: The app is not published/online")
            else:
                print("  -> See: https://open.feishu.cn/document/server-docs/im-v1/message/create")

    except Exception as e:
        print(f"  [ERROR] Exception: {e}")
        import traceback
        traceback.print_exc()

# ──────────────────────────────────────────────────────────
# Step 5: Try sending an interactive card
# ──────────────────────────────────────────────────────────
print(f"\n{'─' * 72}")
print("STEP 5: Send interactive card to LARK_DEFAULT_CHAT_ID")
print(f"{'─' * 72}")

if DEFAULT_CHAT_ID:
    try:
        card_data = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "Diagnostic Card"},
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "This is a **diagnostic** card from test_lark_push.py",
                    },
                },
            ],
        }

        card_content = json.dumps(card_data)

        card_request = CreateMessageRequest.builder() \
            .receive_id_type("chat_id") \
            .request_body(
                CreateMessageRequestBody.builder()
                    .receive_id(DEFAULT_CHAT_ID)
                    .content(card_content)
                    .msg_type("interactive")
                    .build()
            ) \
            .build()

        card_response = client.im.v1.message.create(card_request)

        print(f"  Target:       {DEFAULT_CHAT_ID}")
        print(f"  Msg type:     interactive")
        print(f"  HTTP status:  {card_response.raw.status_code if card_response.raw else 'N/A'}")
        print(f"  code:         {card_response.code}")
        print(f"  msg:          {card_response.msg}")
        print(f"  log_id:       {card_response.get_log_id()}")

        if card_response.raw:
            try:
                raw_body = json.loads(card_response.raw.content)
                print(f"  Raw body:     {json.dumps(raw_body, indent=2, ensure_ascii=False)}")
            except (json.JSONDecodeError, TypeError):
                print(f"  Raw body:     {card_response.raw.content[:500]}")

        if card_response.success():
            print("  [OK] Card sent successfully")
        else:
            print("  [FAIL] Failed to send card")
            if card_response.code == 10003:
                print("  -> INVALID CHAT_ID: The chat_id does not exist")
            elif card_response.code == 99991663:
                print("  -> BOT NOT IN CHAT: The bot is not a member of this chat")
            elif card_response.code == 99991669:
                print("  -> BOT PERMISSION DENIED: Bot lacks permission to send messages")
            elif card_response.code == 99991600:
                print("  -> APP NOT ENABLED: The app is not enabled for this tenant")
            elif card_response.code == 99991601:
                print("  -> APP NOT PUBLISHED: The app is not published/online")
            else:
                print("  -> See: https://open.feishu.cn/document/server-docs/im-v1/message/create")

    except Exception as e:
        print(f"  [ERROR] Exception: {e}")
        import traceback
        traceback.print_exc()

# ──────────────────────────────────────────────────────────
# Step 6: Test FeishuReplyClient wrapper
# ──────────────────────────────────────────────────────────
print(f"\n{'─' * 72}")
print("STEP 6: Test via FeishuReplyClient")
print(f"{'─' * 72}")

if not DEFAULT_CHAT_ID:
    print("  [SKIP] LARK_DEFAULT_CHAT_ID is empty")
else:
    try:
        from bot.platforms.feishu_stream import FeishuReplyClient

        reply_client = FeishuReplyClient(APP_ID, APP_SECRET)
        print("  [OK] FeishuReplyClient created")

        test_card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "FeishuReplyClient Test"},
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "Sent via FeishuReplyClient.send_card()",
                    },
                },
            ],
        }

        # Monkey-patch to capture the raw response
        original_create = client.im.v1.message.create
        captured_response = [None]

        def capturing_create(request):
            resp = original_create(request)
            captured_response[0] = resp
            return resp

        reply_client._client.im.v1.message.create = capturing_create

        ok = reply_client.send_card(test_card, DEFAULT_CHAT_ID)

        print(f"  send_card() returned: {ok}")
        resp = captured_response[0]
        if resp is not None:
            print(f"  Actual SDK response:")
            print(f"    code:         {resp.code}")
            print(f"    msg:          {resp.msg}")
            print(f"    log_id:       {resp.get_log_id()}")
            print(f"    HTTP status:  {resp.raw.status_code if resp.raw else 'N/A'}")
            if resp.raw:
                try:
                    print(f"    Raw body:     {json.dumps(json.loads(resp.raw.content), indent=2, ensure_ascii=False)}")
                except (json.JSONDecodeError, TypeError):
                    print(f"    Raw body:     {resp.raw.content[:500]}")
            print(f"    success():    {resp.success()}")
            if resp.code != 0:
                print(f"  [ODD] API code={resp.code} != 0 but send_card() returned {ok}")
        else:
            print("  (no response captured -- possible exception path)")

    except Exception as e:
        print(f"  [ERROR] Exception: {e}")
        import traceback
        traceback.print_exc()

# ──────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────
print(f"\n{'=' * 72}")
print("DIAGNOSTIC SUMMARY")
print(f"{'=' * 72}")
print("""
If all steps pass (code=0):
  Credentials valid, bot can access API, messages deliverable.
  Check if the bot is added to the target chat/group.

If Step 2 fails:
  LARK_APP_ID or LARK_APP_SECRET is wrong.

If Step 3 fails:
  App may be disabled or lacking tenant permissions.

If Step 4/5 fail:
  code=10003:     chat_id doesn't exist
  code=99991663:  bot NOT a member of the target chat
  code=99991669:  bot lacks message sending permission
  code=99991600:  app not enabled for this tenant
  code=99991601:  app not published yet
  code=99991668:  message content format invalid
""")
