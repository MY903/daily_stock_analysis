# L3: CardActionHandler → SignalConfirmHandler Wiring Evidence

## Summary
Wired FeishuCardActionHandler P2CardActionTriggerV1 callback to SignalConfirmHandler for
full confirm/reject lifecycle with card UI updates.

## Changes

### 1. `bot/platforms/feishu_stream.py` — FeishuReplyClient.update_card()
- Added `update_card(message_id, card) -> bool` method using SDK's
  `UpdateMessageRequest` (PATCH /open-apis/im/v1/messages/:message_id)
- Added `get_card_handler()` accessor on `FeishuStreamClient` for external wiring
- Added `UpdateMessageRequest`/`UpdateMessageRequestBody` imports

### 2. `bot/platforms/lark_interactive.py` — FeishuCardActionHandler callbacks
- Added `_confirm_handler`/`_reject_handler` callable attributes
- Added `set_confirm_handler(handler)`/`set_reject_handler(handler)` methods
- Updated `handle_card_action()` to extract `open_message_id` from event context
- After parsing action & signal_id, calls registered handler with kwargs
  `(signal_id, message_id=..., chat_id=...)`
- Added `LarkCardBuilder.confirmed_card()` — card with "已确认" text, no buttons
- Added `LarkCardBuilder.rejected_card()` — card with "已拒绝" text

### 3. `src/trading/card_handler.py` — SignalConfirmHandler lifecycle
- Added `reply_client` parameter (optional FeishuReplyClient)
- Added `wire_card_action_handler(card_handler)` to bridge callbacks
- `_on_confirm()`: calls `handle_card_action(signal_id, "confirm")` then
  calls `reply_client.update_card()` to replace buttons with "已确认" text
- `_on_reject()`: calls `handle_card_action(signal_id, "reject")` then
  sends new "已拒绝" card via `reply_client.send_card()`

### 4. `src/trading/pipeline.py` — QuantWeaselPipeline
- Added `reply_client` parameter to `__init__`
- Passed `reply_client` to `SignalConfirmHandler`

## Data Flow
```
User clicks button on card
  ↓
SDK → FeishuCardActionHandler.handle_card_action(event)
  ↓  parses action.value {action, signal_id}
  ↓  extracts context.open_message_id, context.open_chat_id
  ↓
if confirm → self._confirm_handler(signal_id, message_id=..., chat_id=...)
if reject  → self._reject_handler(signal_id, message_id=..., chat_id=...)
  ↓
SignalConfirmHandler._on_confirm/reject(signal_id, **kwargs)
  ↓  calls handle_card_action(signal_id, action)
  ↓  → signal.status = CONFIRMED | REJECTED
  ↓  → audit log
  ↓  → (existing) execution trigger if confirm
  ↓
Card UI update:
  Confirm → update_card(message_id, confirmed_card)  // no buttons
  Reject  → send_card(rejected_card, chat_id)         // new message
```

## State Transitions
- Confirm → Signal.status = CONFIRMED (via handle_card_action line 187)
- Reject  → Signal.status = REJECTED  (via handle_card_action line 195)
- Buttons disabled after click via update_card (anti-double-click)

## Verification
- `python -m py_compile` passes on all 4 modified files
- LSP diagnostics: 0 errors across all modified files
- No new execution triggers added (I1's job)
- No git commit made

## Required Wiring at App Level
```python
# After creating both FeishuStreamClient and SignalConfirmHandler:
stream_client = get_feishu_stream_client()
card_handler = stream_client.get_card_handler()
signal_confirm_handler.wire_card_action_handler(card_handler)
```
