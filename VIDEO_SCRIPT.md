# Video Presentation Script

**Update**: this script became a real video — `video/presentation.mp4` (2:34, 8 scenes, one per
slide in `slides/index.html`). Built from this exact narration text via `ffmpeg`'s `libflite`
text-to-speech filter (synthesized voiceover per scene) composited over a screenshot of each
slide, then concatenated. No manual recording was needed in the end. The beat-by-beat breakdown
below is kept as the source-of-truth script the real video was generated from, and as a
reference if you want to re-record a version with your own voice instead.

Regenerate it: for each scene, `ffmpeg -f lavfi -i "flite=text='...'" narration_N.wav` (avoid `:`
and `'` inside the text — the filtergraph parser treats them as syntax), screenshot the matching
slide via `slides/index.html?slide=N`, then `ffmpeg -loop 1 -i slide_N.png -i narration_N.wav
-c:v libx264 -tune stillimage -c:a aac -shortest segment_N.mp4` per scene and concatenate with
the `concat` demuxer.

---

**[0:00–0:15] — Hook, face-to-camera or voiceover over the cover image**

> "I built an autonomous options trading agent where the AI never touches option math or picks a
> strike — it's not allowed to. Here's why, and how it works."

*(Show: `cover.png`)*

---

**[0:15–0:45] — The architecture**

> "Every decision runs through three layers. The Analyst is an LLM — it debates market regime, bull
> case, bear case — but it's advisory only, it can never approve or block a trade. The Governor is
> deterministic Python: real Black-Scholes math, real strike selection off the live option chain.
> The Executor validates the order against a strict schema, then submits it as one atomic multi-leg
> order through the Alpaca CLI."

*(Show: slide 2 from `slides/deck.pdf` — the pipeline diagram)*

---

**[0:45–1:15] — Why advisory-only, with the real story**

> "I didn't just decide this in theory — I tested it. Same LLM, same day, two live runs. Once it
> correctly caught a real risk: an options expiry landing on Non-Farm Payrolls day. The next run,
> it confidently cited a Labor Day date that was just wrong — off by three days. One real catch,
> one hallucination, same model. That's exactly why it narrates but never decides."

*(Show: terminal or a snippet of `architecture-decisions.md`'s "Live agent" section)*

---

**[1:15–1:45] — The strategy and the backtest**

> "The strategy itself is a market-neutral SPY iron condor — sell premium only when implied vol is
> rich relative to realized vol, and skew isn't elevated. Backtested against a full year of real
> Alpaca historical option data: Sharpe 2.53, 90.9% win rate, under 2% max drawdown. I also tested
> four more aggressive, directional strategies specifically to see if something could beat the
> index outright — none did once tested for real, and the most promising one on paper was actually
> the worst performer once real data hit it."

*(Show: slide 4 and slide 5 from `slides/deck.pdf` — backtest results, due diligence)*

---

**[1:45–2:15] — It's actually running**

> "This isn't a backtest-only submission. It's live right now — GitHub Actions runs the agent every
> 15 minutes during market hours against a dedicated paper account, and commits a full audit log
> back to the repo after every single cycle, including the cycles where it decides to do nothing."

*(Show: the live dashboard at your deployed Netlify URL, or `dashboard/index.html` opened locally —
scroll through the audit trail feed)*

---

**[2:15–2:30] — Close**

> "Full write-up, backtest data, and the live audit trail are all in the repo. Thanks for watching."

*(Show: repo URL on screen — github.com/adwik1401/alpaca-ai-trading-agent)*

---

## Recording notes

- Screen recording tool: OBS Studio (free) or Windows' built-in Xbox Game Bar (`Win+G`) both work
  fine for a straightforward screen-cap-plus-voiceover.
- Keep it under 3 minutes — judges are reviewing many submissions.
- If you don't want to be on camera, a voiceover over the slides/dashboard is completely fine — the
  script above already assumes that.
