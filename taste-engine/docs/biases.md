# Biases: what is recorded, and how it is processed

Votes measure taste, but other things lean on them too: which side a site was on, the screen it
was seen on, how tired the voter was, how much they looked. This document lists each bias and three
things about it:

- where its data is recorded;
- what processes it today (`taste votes agreement` prints every view named here);
- how training will correct for it.

Nothing about this is shown to voters while they vote.

## Where the data lives

| Data | Recorded in | Written by |
|---|---|---|
| Which capture was on which side, and the verdict | `votes.left_capture`, `right_capture`, `outcome` | `cast_vote` |
| When the pair was served and how long the vote took (wall-clock) | `served_pairs.served_at`, `votes.seconds_to_vote` | `next_pair`, `cast_vote` |
| How long the pair was really looked at: seconds on screen (`visible_s`), in front (`focused_s`) and in use (`active_s`, up to `idle_cutoff_seconds` after the last input or a playing reel); times the voter left the page (`away_count`) or switched window (`blur_count`); the longest stretch on screen without input; reloads (`resumed`) | `votes.client.timing` | The voting page, sent with each vote |
| Whether a reason was asked for | `served_pairs.reason_requested` | `next_pair` |
| Listed dimensions and the voter's own words | `votes.dimensions`, `votes.own_terms` | `cast_vote` |
| How the vote was cast: session, position in the session, layout (`tabs`, `stacked`, `side_by_side`), screen size, pixel ratio, touch or mouse | `votes.client` (an open object; new keys need no schema change) | The voting page, sent with each vote |
| What the voter looked at: phone tab opened, screens scrolled, reels played, live site opened | `vote_events` (`view_*`, `scroll_*`, `play_*`, `open_live_*`) | The voting page, as it happens |
| The page's language, and whether anything covered it | `captures.description` (`language`, `obstruction`, `page_state`) | `taste describe`, then `taste publish` |

Wall-clock time also counts a tab left open overnight; active time does not. The limits (the
size of `client`, the low-effort threshold, the idle cut-off, the gap that starts a new sitting)
live in `voting_config`, and each
round's vote target in `round_targets`. `voting_facts()` gathers them for `/api/config`, which the
voting page and the voter guide both read; the dimension definitions come from `dimensions`.

## Each bias

| Bias | Prevented by | Measured by | Corrected in training by |
|---|---|---|---|
| **Position.** Favouring a side | Balanced sides: each site goes on the side it has been on less (`next_pair`); repeats swap sides | `voter_bias.left_share` (near 0.5 means no lean), split by layout; `voter_consistency` on swapped repeats | A side term in the pairwise model (P(left wins) has its own offset), fitted per voter if they differ |
| **Device and layout.** One site at a time on a phone, both at once on a desktop | — | `voter_bias` is split by `layout`; `client.viewport_width` | Layout as a covariate; votes cast without seeing both sites are down-weighted |
| **Not looking at both sites.** Phones show A first | — | `vote_attention.saw_both`, `voter_bias.saw_both_share` | Votes where B was never opened are dropped or down-weighted |
| **Hero only.** Judging the first screen and never scrolling | — | `vote_attention.scrolled_both`, `voter_bias.scrolled_both_share` (visual) | A weight by attention; compare models trained with and without these votes |
| **Motion judged without watching** | — | `vote_attention.played_both`, `voter_bias.played_both_share` (motion) | Motion votes count only when both reels were played |
| **Fatigue** | Guide: sessions of 20–30 votes; calibration order shuffled per voter | `voter_effort`: early vs late median active time within sittings (a new sitting starts after `session_gap_minutes` without a vote, whatever the tab); `client.index` per vote | A weight that falls with position in a long sitting; or drop votes past a measured point |
| **Idle time counted as effort.** A tab left open, a break mid-pair | Guide: breaks are fine, time away is not counted | `vote_attention.active_seconds`, `left_page`; `voter_effort.idle_votes` (wall-clock exceeds active time by more than the cut-off), `left_page_votes`; `voter_bias.left_page_share` | Use active time, never wall-clock, for effort and fatigue; votes cast before timing existed are capped or left out of time-based weights |
| **Low effort** | Votes under 1 s are refused (`min_vote_seconds`) | `voter_effort.fast_votes` (under `fast_vote_seconds`), `voter_consistency` | Per-voter reliability weights from calibration |
| **Ties and "can't decide" as an easy way out** | All four outcomes look the same; both may say why (optional) | `voter_bias.tie_share`, `cant_decide_share`; their words and reasons in `votes` | Ties are half-wins; "can't decide" is left out of preference labels, but its words show which trade-off was hard |
| **Priming by the listed dimensions** | Own words are always offered; suggestions come only from the voter's own past words | `voter_bias.own_words_share` | Themes are found from own words and reasons, not imposed |
| **Being asked for a reason** | Asked at random, plus on split pairs, never explained | `served_pairs.reason_requested` against outcome and time | A covariate in the analysis: do asked votes differ? |
| **Visual verdict colouring the motion verdict** | Run the rounds in separate sessions | `round_differences`, including `same_session` | Compare same-session and separate-session differences |
| **Brand recognition** | The guide asks voters to judge craft | `vote_attention.opened_live`, `voter_bias.opened_live_share` | Compare famous and unknown sites' win rates; a brand covariate if it matters |
| **Language** | — | `language_bias` (win share by page language) | A language covariate if a lean appears |
| **Voter taste** (signal, not noise) | Calibration pairs every voter judges | `voter_agreement`, `pair_agreement` | Voter identity in the model: per-voter scores, not one averaged truth |

## The order of processing

1. **During voting**, run `taste votes agreement` after each voting day. It prints panel agreement,
   consistency, effort and fatigue, bias by layout, and wins by language.
2. **After voting**, run `taste votes export`. It writes `votes.jsonl`, with `client` on every vote,
   and `vote_events.jsonl`.
3. **The cleaning and weighting step** (to build) reads those files and the same rules as the views
   above. It writes one weight per vote, with the reason for each weight, so every exclusion is
   explainable.
4. **Training** uses the weights and the covariates named in the last column above.
