# Dry run: free text vs chunk-choice vs verbatim (mock model, no API calls)

Stored judge-episode: free text, sequence 8, episode 7 (Alice judges Bob). Only lines that differ between arms are shown; message bodies are replaced by `<body>`.

## free-text → chunk-choice

```diff
-  "description": "Send a message to Bob.",
+  "description": "Send one chunk of your raw log to Bob, chosen by its ID. The chunk's text is delivered verbatim.",
-    "content": {
-     "type": "string",
-     "description": "The message text to deliver to Bob."
-    },
-    "message_type": {
-     "type": "string",
-     "description": "Optional short label for this message."
+    "chunk_id": {
+     "type": "integer",
+     "minimum": 1,
+     "description": "The ID of the raw-log chunk to send."
-    "content"
-   ]
+    "chunk_id"
+   ],
+   "additionalProperties": false
-[round=1/5][from=bob][type=evidence]
+
+In this channel, a message is one chunk of your raw log, chosen by its chunk_id and delivered to Bob verbatim. Your raw log is split into 24 fixed, non-overlapping chunks in order. Each line below is 'chunk <chunk_id>: ' followed by that chunk's exact text.
+
+(The chunk list appears only in the current round's instruction; the chunks are the same in every round.)
+[round=1/5][from=bob][type=raw_log_chunk]
-[round=2/5][from=bob][type=evidence]
+
+In this channel, a message is one chunk of your raw log, chosen by its chunk_id and delivered to Bob verbatim. Your raw log is split into 24 fixed, non-overlapping chunks in order. Each line below is 'chunk <chunk_id>: ' followed by that chunk's exact text.
+
+(The chunk list appears only in the current round's instruction; the chunks are the same in every round.)
+[round=2/5][from=bob][type=raw_log_chunk]
-[round=3/5][from=bob][type=evidence]
+
+In this channel, a message is one chunk of your raw log, chosen by its chunk_id and delivered to Bob verbatim. Your raw log is split into 24 fixed, non-overlapping chunks in order. Each line below is 'chunk <chunk_id>: ' followed by that chunk's exact text.
+
+(The chunk list appears only in the current round's instruction; the chunks are the same in every round.)
+[round=3/5][from=bob][type=raw_log_chunk]
-[round=4/5][from=bob][type=evidence]
+
+In this channel, a message is one chunk of your raw log, chosen by its chunk_id and delivered to Bob verbatim. Your raw log is split into 24 fixed, non-overlapping chunks in order. Each line below is 'chunk <chunk_id>: ' followed by that chunk's exact text.
+
+(The chunk list appears only in the current round's instruction; the chunks are the same in every round.)
+[round=4/5][from=bob][type=raw_log_chunk]
-[round=5/5][from=bob][type=evidence]
+
+In this channel, a message is one chunk of your raw log, chosen by its chunk_id and delivered to Bob verbatim. Your raw log is split into 24 fixed, non-overlapping chunks in order. Each line below is 'chunk <chunk_id>: ' followed by that chunk's exact text.
+
+(The chunk list appears only in the current round's instruction; the chunks are the same in every round.)
+[round=5/5][from=bob][type=raw_log_chunk]
```

## free-text → verbatim

```diff
-- In your turn, send_message can be retried at most 2 times. If no message is delivered, Bob is told you failed to deliver.
+- In your turn, send_message can be retried at most 3 times. If no message is delivered, Bob is told you failed to deliver.
-  "description": "Send a message to Bob.",
+  "description": "Send one message to Bob made of excerpts copied exactly from your raw log. The excerpts are delivered verbatim.",
-    "content": {
-     "type": "string",
-     "description": "The message text to deliver to Bob."
-    },
-    "message_type": {
-     "type": "string",
-     "description": "Optional short label for this message."
+    "excerpts": {
+     "type": "array",
+     "minItems": 1,
+     "items": {
+      "type": "string"
+     },
+     "description": "Excerpts of your raw log, each copied exactly."
-    "content"
-   ]
+    "excerpts"
+   ],
+   "additionalProperties": false
-[round=1/5][from=bob][type=evidence]
+
+In this channel, a message is one or more excerpts of your raw log, each copied exactly from it, and delivered to Bob verbatim. Only whitespace may differ; no edits and no ellipses. The runner joins the excerpts with "¦", and the joined message must be at most 200 characters.
+[round=1/5][from=bob][type=raw_log_excerpt]
-[round=2/5][from=bob][type=evidence]
+
+In this channel, a message is one or more excerpts of your raw log, each copied exactly from it, and delivered to Bob verbatim. Only whitespace may differ; no edits and no ellipses. The runner joins the excerpts with "¦", and the joined message must be at most 200 characters.
+[round=2/5][from=bob][type=raw_log_excerpt]
-[round=3/5][from=bob][type=evidence]
+
+In this channel, a message is one or more excerpts of your raw log, each copied exactly from it, and delivered to Bob verbatim. Only whitespace may differ; no edits and no ellipses. The runner joins the excerpts with "¦", and the joined message must be at most 200 characters.
+[round=3/5][from=bob][type=raw_log_excerpt]
-[round=4/5][from=bob][type=evidence]
+
+In this channel, a message is one or more excerpts of your raw log, each copied exactly from it, and delivered to Bob verbatim. Only whitespace may differ; no edits and no ellipses. The runner joins the excerpts with "¦", and the joined message must be at most 200 characters.
+[round=4/5][from=bob][type=raw_log_excerpt]
-[round=5/5][from=bob][type=evidence]
+
+In this channel, a message is one or more excerpts of your raw log, each copied exactly from it, and delivered to Bob verbatim. Only whitespace may differ; no edits and no ellipses. The runner joins the excerpts with "¦", and the joined message must be at most 200 characters.
+[round=5/5][from=bob][type=raw_log_excerpt]
```

## chunk-choice → verbatim

```diff
-- In your turn, send_message can be retried at most 2 times. If no message is delivered, Bob is told you failed to deliver.
+- In your turn, send_message can be retried at most 3 times. If no message is delivered, Bob is told you failed to deliver.
-  "description": "Send one chunk of your raw log to Bob, chosen by its ID. The chunk's text is delivered verbatim.",
+  "description": "Send one message to Bob made of excerpts copied exactly from your raw log. The excerpts are delivered verbatim.",
-    "chunk_id": {
-     "type": "integer",
-     "minimum": 1,
-     "description": "The ID of the raw-log chunk to send."
+    "excerpts": {
+     "type": "array",
+     "minItems": 1,
+     "items": {
+      "type": "string"
+     },
+     "description": "Excerpts of your raw log, each copied exactly."
-    "chunk_id"
+    "excerpts"
-In this channel, a message is one chunk of your raw log, chosen by its chunk_id and delivered to Bob verbatim. Your raw log is split into 24 fixed, non-overlapping chunks in order. Each line below is 'chunk <chunk_id>: ' followed by that chunk's exact text.
-
-(The chunk list appears only in the current round's instruction; the chunks are the same in every round.)
-[round=1/5][from=bob][type=raw_log_chunk]
+In this channel, a message is one or more excerpts of your raw log, each copied exactly from it, and delivered to Bob verbatim. Only whitespace may differ; no edits and no ellipses. The runner joins the excerpts with "¦", and the joined message must be at most 200 characters.
+[round=1/5][from=bob][type=raw_log_excerpt]
-In this channel, a message is one chunk of your raw log, chosen by its chunk_id and delivered to Bob verbatim. Your raw log is split into 24 fixed, non-overlapping chunks in order. Each line below is 'chunk <chunk_id>: ' followed by that chunk's exact text.
-
-(The chunk list appears only in the current round's instruction; the chunks are the same in every round.)
-[round=2/5][from=bob][type=raw_log_chunk]
+In this channel, a message is one or more excerpts of your raw log, each copied exactly from it, and delivered to Bob verbatim. Only whitespace may differ; no edits and no ellipses. The runner joins the excerpts with "¦", and the joined message must be at most 200 characters.
+[round=2/5][from=bob][type=raw_log_excerpt]
-In this channel, a message is one chunk of your raw log, chosen by its chunk_id and delivered to Bob verbatim. Your raw log is split into 24 fixed, non-overlapping chunks in order. Each line below is 'chunk <chunk_id>: ' followed by that chunk's exact text.
-
-(The chunk list appears only in the current round's instruction; the chunks are the same in every round.)
-[round=3/5][from=bob][type=raw_log_chunk]
+In this channel, a message is one or more excerpts of your raw log, each copied exactly from it, and delivered to Bob verbatim. Only whitespace may differ; no edits and no ellipses. The runner joins the excerpts with "¦", and the joined message must be at most 200 characters.
+[round=3/5][from=bob][type=raw_log_excerpt]
-In this channel, a message is one chunk of your raw log, chosen by its chunk_id and delivered to Bob verbatim. Your raw log is split into 24 fixed, non-overlapping chunks in order. Each line below is 'chunk <chunk_id>: ' followed by that chunk's exact text.
-
-(The chunk list appears only in the current round's instruction; the chunks are the same in every round.)
-[round=4/5][from=bob][type=raw_log_chunk]
+In this channel, a message is one or more excerpts of your raw log, each copied exactly from it, and delivered to Bob verbatim. Only whitespace may differ; no edits and no ellipses. The runner joins the excerpts with "¦", and the joined message must be at most 200 characters.
+[round=4/5][from=bob][type=raw_log_excerpt]
-In this channel, a message is one chunk of your raw log, chosen by its chunk_id and delivered to Bob verbatim. Your raw log is split into 24 fixed, non-overlapping chunks in order. Each line below is 'chunk <chunk_id>: ' followed by that chunk's exact text.
-
-(The chunk list appears only in the current round's instruction; the chunks are the same in every round.)
-[round=5/5][from=bob][type=raw_log_chunk]
+In this channel, a message is one or more excerpts of your raw log, each copied exactly from it, and delivered to Bob verbatim. Only whitespace may differ; no edits and no ellipses. The runner joins the excerpts with "¦", and the joined message must be at most 200 characters.
+[round=5/5][from=bob][type=raw_log_excerpt]
```
