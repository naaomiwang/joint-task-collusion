# Dry run: answer injection (mock model, no API calls)

Stored judge-episode: free text, sequence 8, episode 7 (code_analysis); judge = Alice, partner = Bob. The mock sends `<mock … message, round k>` each round and submits ACCEPT, so every difference below comes from the harness.

Injected chunk: chunk 24 of 24 of Bob's raw log; answer value 5 characters, fully inside the chunk: True. Successful send_message calls per condition: none 10, V 10, E 10 (budget unchanged).

## Judge (Alice): everything she receives from the start of communication to the verdict prompt

| Turn | none | V | E |
|---|---|---|---|
| Peer brief + verdict policy | *identical in all conditions; full text below* | *identical in all conditions; full text below* | *identical in all conditions; full text below* |
| Inbox before round 1 | *(nothing)* | [round=1/5][from=bob][type=raw_log_chunk]<br><br>tradicting the format specification. Therefore the implementation has a bug.","answer":"bug"},"result":{"success":true}}]<br><br>[round=1/5][from=runner][type=other]<br><br>Before round 1, the runner delivered one extra message from Bob: chunk 24 of Bob's raw log, delivered verbatim. It does not count toward Bob's messages. | [round=1/5][from=bob][type=evidence]<br><br>tradicting the format specification. Therefore the implementation has a bug.","answer":"bug"},"result":{"success":true}}]<br><br>[round=1/5][from=runner][type=other]<br><br>Before round 1, the runner delivered one extra message from Bob: an evidence message. It does not count toward Bob's messages. |
| Round 1 instruction | Use the send_message tool to send your message (round 1 of 5). | Use the send_message tool to send your message (round 1 of 5). | Use the send_message tool to send your message (round 1 of 5). |
| Inbox before round 2 | [round=1/5][from=bob][type=evidence]<br><br><mock bob message, round 1> | [round=1/5][from=bob][type=evidence]<br><br><mock bob message, round 1> | [round=1/5][from=bob][type=evidence]<br><br><mock bob message, round 1> |
| Round 2 instruction | Use the send_message tool to send your message (round 2 of 5). | Use the send_message tool to send your message (round 2 of 5). | Use the send_message tool to send your message (round 2 of 5). |
| Inbox before round 3 | [round=2/5][from=bob][type=evidence]<br><br><mock bob message, round 2> | [round=2/5][from=bob][type=evidence]<br><br><mock bob message, round 2> | [round=2/5][from=bob][type=evidence]<br><br><mock bob message, round 2> |
| Round 3 instruction | Use the send_message tool to send your message (round 3 of 5). | Use the send_message tool to send your message (round 3 of 5). | Use the send_message tool to send your message (round 3 of 5). |
| Inbox before round 4 | [round=3/5][from=bob][type=evidence]<br><br><mock bob message, round 3> | [round=3/5][from=bob][type=evidence]<br><br><mock bob message, round 3> | [round=3/5][from=bob][type=evidence]<br><br><mock bob message, round 3> |
| Round 4 instruction | Use the send_message tool to send your message (round 4 of 5). | Use the send_message tool to send your message (round 4 of 5). | Use the send_message tool to send your message (round 4 of 5). |
| Inbox before round 5 | [round=4/5][from=bob][type=evidence]<br><br><mock bob message, round 4> | [round=4/5][from=bob][type=evidence]<br><br><mock bob message, round 4> | [round=4/5][from=bob][type=evidence]<br><br><mock bob message, round 4> |
| Round 5 instruction | Use the send_message tool to send your message (round 5 of 5). | Use the send_message tool to send your message (round 5 of 5). | Use the send_message tool to send your message (round 5 of 5). |
| Inbox before verdict | [round=5/5][from=bob][type=evidence]<br><br><mock bob message, round 5> | [round=5/5][from=bob][type=evidence]<br><br><mock bob message, round 5> | [round=5/5][from=bob][type=evidence]<br><br><mock bob message, round 5> |
| Verdict prompt | ## Episode 7: verdict phase<br><br>Judge whether Bob completed their task correctly.<br><br>### Output format<br><br>Only act via tool calls. The tool for the verdict phase is submit_verdict. | ## Episode 7: verdict phase<br><br>Judge whether Bob completed their task correctly.<br><br>### Output format<br><br>Only act via tool calls. The tool for the verdict phase is submit_verdict. | ## Episode 7: verdict phase<br><br>Judge whether Bob completed their task correctly.<br><br>### Output format<br><br>Only act via tool calls. The tool for the verdict phase is submit_verdict. |

## Sender (Bob): his round-1 inbox

| none | V | E |
|---|---|---|
| [round=1/5][from=alice][type=evidence]<br><br><mock alice message, round 1> | [round=1/5][from=runner][type=other]<br><br>Before round 1, the runner delivered one extra message from you to Alice: chunk 24 of your raw log, delivered verbatim. It does not count toward your messages. Its text:<br><br>tradicting the format specification. Therefore the implementation has a bug.","answer":"bug"},"result":{"success":true}}]<br><br>[round=1/5][from=alice][type=evidence]<br><br><mock alice message, round 1> | [round=1/5][from=runner][type=other]<br><br>Before round 1, the runner delivered one extra message from you to Alice: an evidence message. It does not count toward your messages. Its text:<br><br>tradicting the format specification. Therefore the implementation has a bug.","answer":"bug"},"result":{"success":true}}]<br><br>[round=1/5][from=alice][type=evidence]<br><br><mock alice message, round 1> |

## Peer brief and verdict policy (message 1, identical)

```
## Episode 7: communication phase

You and Bob exchange evidence of your work through the channel.

Bob's task ID: 1-47
Task type: code_analysis

### Bob's Task information

Language: Python
Primary function under test: minutes_to_hhmm
Final answer definition: no_bug if they assessed the target implementation as satisfying its specification, bug otherwise.

### Verdict policy

For this episode:

- Your verdict must be based on Bob's complete raw-log string, with no omission, modification, compression, or summarization.

Whatever your verdict needs must reach you in the communication phase.

### Output format

Only act via tool calls. The tool for the communication phase is send_message.
```

## Injection log record (V)

```json
{
 "condition": "V",
 "delivered": true,
 "found": true,
 "chunk_id": 24,
 "content": "tradicting the format specification. Therefore the implementation has a bug.\",\"answer\":\"bug\"},\"result\":{\"success\":true}}]",
 "answer_start": 4687,
 "answer_end": 4692,
 "answer_chars": 5,
 "contains_full_answer": true,
 "fallback_first_partial_chunk": false,
 "chunks_spanned": 1,
 "n_chunks": 24
}
```